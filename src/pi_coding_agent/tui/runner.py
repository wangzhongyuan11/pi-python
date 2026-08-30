"""Real interactive process loop built on the shared SDK and product TUI."""

from __future__ import annotations

import asyncio
import base64
import os
import shutil
import sys
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol, TextIO, cast, runtime_checkable
from uuid import uuid4

from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document

from pi_agent import AgentMessage
from pi_ai import (
    AssistantMessage,
    CredentialResolver,
    ImageContent,
    JsonValue,
    ModelThinkingLevel,
    TextContent,
    UserMessage,
    clamp_thinking_level,
)
from pi_tui.render import InlineRenderer, ScreenRenderer

from ..agent_session import AgentSession
from ..attachments import (
    build_image_attachment,
    build_text_file_attachment,
    classify_attachment,
    supports_image_input,
)
from ..cli.run import HeadlessOptions, resolve_session_manager
from ..extensions.registry import CapabilityRegistry
from ..model_runtime import ModelRuntime, create_model_runtime, match_model_argument
from ..sdk import (
    CreateAgentSessionOptions,
    ToolSelection,
    create_agent_session,
    default_session_dir,
)
from ..session.catalog import SessionSummary, list_sessions
from ..session.errors import SessionNotFoundError
from .commands import CommandDispatcher, CommandOutcome, CommandSpec
from .config_ui import ModelSettingsController
from .main import InteractiveApp
from .render_messages import render_replay_lines
from .session_ui import fork_from, switch_to

type ReadLine = Callable[[str], Awaitable[str | None]]
type ReadChar = Callable[[], str | None]

_MAX_IMAGE_BYTES = 10 * 1024 * 1024

_KEY_POLL_INTERVAL_SECONDS = 0.02

_WIN32_ENABLE_PROCESSED_INPUT = 0x0001


def _disable_console_interrupt() -> Callable[[], None] | None:
    """Temporarily deliver Ctrl+C as a plain key instead of a SIGINT signal.

    Returns a restore callable, or ``None`` when stdin is not a real console
    (piped input, tests). The key poller can then observe ``\\x03`` and abort
    the running turn gracefully instead of the process dying mid-stream.
    """

    try:
        if not sys.stdin.isatty():
            return None
    except (AttributeError, OSError, ValueError):
        return None
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return None
        original = mode.value
        if original & _WIN32_ENABLE_PROCESSED_INPUT:
            kernel32.SetConsoleMode(handle, original & ~_WIN32_ENABLE_PROCESSED_INPUT)

        def restore_windows() -> None:
            kernel32.SetConsoleMode(handle, original)

        return restore_windows
    import termios

    try:
        attributes = termios.tcgetattr(sys.stdin.fileno())
    except (OSError, termios.error, ValueError):
        return None
    if attributes[3] & termios.ISIG:
        attributes[3] &= ~termios.ISIG
        try:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, attributes)
        except (OSError, termios.error):
            return None

        def restore_posix() -> None:
            attributes[3] |= termios.ISIG
            try:
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, attributes)
            except (OSError, termios.error):
                pass

        return restore_posix
    return None


def _console_char_reader() -> ReadChar | None:
    """Non-blocking console key reader for interrupting running turns.

    Returns ``None`` when stdin is not an interactive console (piped input,
    tests, smoke harnesses) so the turn loop keeps its previous behavior.
    """

    try:
        if not sys.stdin.isatty():
            return None
    except (AttributeError, OSError, ValueError):
        return None
    if sys.platform == "win32":
        import msvcrt

        try:
            msvcrt.kbhit()
        except (OSError, ValueError):
            return None

        def read_char_windows() -> str | None:
            return msvcrt.getwch() if msvcrt.kbhit() else None

        return read_char_windows
    import select
    import termios
    import tty

    try:
        tty.setcbreak(sys.stdin.fileno())
    except (OSError, ValueError, termios.error):
        return None

    def read_char_posix() -> str | None:
        ready, _, _ = select.select([sys.stdin], [], [], 0)
        if not ready:
            return None
        return os.read(sys.stdin.fileno(), 1).decode("utf-8", errors="ignore") or None

    return read_char_posix


async def _drive_turn(
    app: InteractiveApp,
    session: AgentSession,
    line: str,
    read_char: ReadChar | None,
) -> None:
    """Run one user turn, polling console keys for interrupt/steer input."""

    if read_char is None:
        await app.handle(line)
        return
    restore_interrupt = _disable_console_interrupt()
    try:
        await _drive_turn_with_polling(app, session, line, read_char)
    finally:
        if restore_interrupt is not None:
            restore_interrupt()


async def _drive_turn_with_polling(
    app: InteractiveApp,
    session: AgentSession,
    line: str,
    read_char: ReadChar,
) -> None:
    stop_polling = asyncio.Event()
    abort_requested = asyncio.Event()
    typed: list[str] = []

    async def poll_keys() -> None:
        while not stop_polling.is_set():
            char = read_char()
            if char is None:
                await asyncio.sleep(_KEY_POLL_INTERVAL_SECONDS)
                continue
            if char == "\x03":
                abort_requested.set()
                session.abort()
                break
            if char == "\x1b":
                # A lone ESC aborts; ESC followed by [ or O is a CSI/SS3
                # key sequence (arrows etc.) and must not cancel the turn.
                if read_char() in ("[", "O"):
                    read_char()
                    await asyncio.sleep(0)
                    continue
                abort_requested.set()
                session.abort()
                break
            if char in ("\r", "\n"):
                text = "".join(typed).strip()
                typed.clear()
                if text:
                    message = UserMessage(
                        content=(TextContent(text=text),),
                        timestamp=_message_timestamp(),
                    )
                    session.agent.steer(message)
                    app.note(f"steered: {text}")
                await asyncio.sleep(0)
                continue
            typed.append(char)
            # Yield to the event loop so a burst of buffered keys cannot
            # starve the running agent turn.
            await asyncio.sleep(0)

    turn = asyncio.create_task(app.handle(line))
    poller = asyncio.create_task(poll_keys())
    try:
        await turn
    finally:
        stop_polling.set()
        poller.cancel()
        try:
            await poller
        except asyncio.CancelledError:
            pass
    if abort_requested.is_set() and _last_stop_reason(session) == "aborted":
        app.note("cancelled")


def _last_stop_reason(session: AgentSession) -> str | None:
    for message in reversed(session.state.messages):
        if isinstance(message, AssistantMessage):
            return message.stop_reason
    return None


@dataclass(frozen=True, slots=True)
class _PathRef:
    """Minimal session reference for selector actions."""

    path: Path


def _message_timestamp() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


@runtime_checkable
class _HasRegistry(Protocol):
    @property
    def registry(self) -> CapabilityRegistry: ...


class _RawOutput(Protocol):
    def write_raw(self, data: str) -> None: ...

    def flush(self) -> None: ...


def _create_windows_output(output: TextIO) -> _RawOutput:
    from prompt_toolkit.output.windows10 import Windows10_Output

    # Windows10_Output delegates write_raw through __getattr__ to its VT100 port.
    return cast("_RawOutput", Windows10_Output(output))


def _create_output_port(output: TextIO) -> _RawOutput:
    if not output.isatty():
        from prompt_toolkit.output.plain_text import PlainTextOutput

        return cast("_RawOutput", PlainTextOutput(output))
    if sys.platform == "win32":
        return _create_windows_output(output)
    from prompt_toolkit.output.defaults import create_output

    return create_output(stdout=output)


@dataclass(frozen=True, slots=True, kw_only=True)
class InteractiveOptions:
    cwd: Path
    credential_resolver: CredentialResolver
    provider_id: str = "deepseek"
    model_id: str | None = None
    thinking_level: ModelThinkingLevel = "high"
    no_session: bool = False
    session: str | None = None
    resume: bool = False
    session_dir: Path | None = None
    model_runtime: ModelRuntime | None = None
    tui_mode: Literal["regular", "fullscreen"] = "regular"
    tool_selection: ToolSelection | None = None


class _StreamTerminal:
    __slots__ = ("_fullscreen", "_output")

    def __init__(
        self,
        output: TextIO,
        *,
        fullscreen: bool,
        output_port: _RawOutput | None = None,
    ) -> None:
        if output_port is None:
            output_port = _create_output_port(output)
        self._output = output_port
        self._fullscreen = fullscreen

    @property
    def columns(self) -> int:
        return max(1, shutil.get_terminal_size(fallback=(80, 24)).columns)

    @property
    def rows(self) -> int:
        return max(1, shutil.get_terminal_size(fallback=(80, 24)).lines)

    def write(self, data: str) -> None:
        self._output.write_raw(data)
        self._output.flush()

    def move_by(self, lines: int) -> None:
        if lines < 0:
            self.write(f"\x1b[{-lines}A")
        elif lines > 0:
            self.write(f"\x1b[{lines}B")

    def clear_line(self) -> None:
        self.write("\r\x1b[K")

    def clear_from_cursor(self) -> None:
        self.write("\x1b[J")

    def clear_screen(self) -> None:
        if self._fullscreen:
            self.write("\x1b[2J\x1b[H")

    def start(self) -> None:
        if self._fullscreen:
            self.write("\x1b[?1049h")

    def stop(self) -> None:
        if self._fullscreen:
            self.write("\x1b[?1049l")


_TUI_COMMANDS: tuple[tuple[str, str], ...] = (
    ("/help", "show commands"),
    ("/model [provider/model]", "show or switch model"),
    ("/thinking [level]", "show or set thinking level"),
    ("/attach <path>", "attach a file or image to the next prompt"),
    ("/copy", "copy the last reply to the terminal clipboard (OSC-52)"),
    ("/sessions", "list saved sessions and switch by number"),
    ("/fork", "fork the current session and switch to the copy"),
    ("/exit", "leave the session"),
    ("/quit", "leave the session"),
)

_THINKING_LEVEL_CHOICES = ("off", "minimal", "low", "medium", "high", "xhigh", "max")


class SlashCompleter(Completer):
    """prompt_toolkit completer: suggests slash commands and their arguments."""

    def __init__(
        self,
        *,
        commands: tuple[tuple[str, str], ...] = _TUI_COMMANDS,
        models: tuple[str, ...] = (
            "deepseek/deepseek-v4-flash",
            "deepseek/deepseek-v4-pro",
        ),
        thinking_levels: tuple[str, ...] = _THINKING_LEVEL_CHOICES,
    ) -> None:
        self._commands = commands
        self._models = models
        self._thinking_levels = thinking_levels

    def get_completions(  # noqa: E501 (signature must match prompt_toolkit's Completer)
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterable[Completion]:
        text = document.text_before_cursor
        if not text.startswith("/"):
            return ()
        head, _, argument = text.partition(" ")
        if argument or " " in text:
            return list(self._argument_completions(head, argument))
        return [
            Completion(name, start_position=-len(head), display=name, display_meta=meta)
            for name, meta in self._commands
            if name.split(" ", 1)[0].startswith(head)
        ]

    def _argument_completions(self, head: str, argument: str) -> Iterable[Completion]:
        lowered = argument.casefold()
        if head == "/model":
            for model in self._models:
                if not lowered or lowered in model.casefold():
                    yield Completion(
                        model, start_position=-len(argument), display=model, display_meta="model"
                    )
        elif head == "/thinking":
            for level in self._thinking_levels:
                if level.startswith(argument):
                    yield Completion(
                        level,
                        start_position=-len(argument),
                        display=level,
                        display_meta="thinking level",
                    )


def _prompt_toolkit_reader() -> ReadLine:
    from prompt_toolkit import PromptSession

    session: PromptSession[str] = PromptSession(
        completer=SlashCompleter(),
        complete_while_typing=True,
    )

    async def read_line(prompt: str) -> str | None:
        try:
            return await session.prompt_async(prompt)
        except EOFError:
            return None

    return read_line


async def run_interactive(
    options: InteractiveOptions,
    *,
    stdout: TextIO,
    stderr: TextIO,
    read_line: ReadLine | None = None,
    read_char: ReadChar | None = None,
) -> int:
    if sys.platform == "darwin":
        stderr.write("interactive mode is not supported on macOS\n")
        return 2
    runtime = options.model_runtime
    if runtime is None:
        runtime = create_model_runtime(
            credential_resolver=options.credential_resolver,
            provider_id=options.provider_id,
            model_id=options.model_id,
        )
    elif options.model_id is not None:
        runtime.select_model(options.model_id, provider_id=options.provider_id)
    thinking = clamp_thinking_level(runtime.model, options.thinking_level)
    session_dir = options.session_dir
    if options.resume and session_dir is None and options.session is None:
        session_dir = default_session_dir(options.cwd)
    try:
        manager = resolve_session_manager(
            HeadlessOptions(
                cwd=options.cwd,
                prompt="",
                mode="text",
                credential_resolver=options.credential_resolver,
                provider_id=options.provider_id,
                model_id=options.model_id,
                thinking_level=thinking,
                no_session=options.no_session,
                session=options.session,
                resume=options.resume,
                session_dir=session_dir,
                model_runtime=runtime,
            )
        )
    except SessionNotFoundError as error:
        if not options.resume:
            raise
        # Nothing persisted for this directory yet (e.g. the previous run was
        # cancelled before its first assistant message). Start fresh instead
        # of crashing with a traceback.
        stderr.write(f"{error}\nstarting a new session for this directory\n")
        stderr.flush()
        manager = None
    selection = options.tool_selection or ToolSelection()
    created = await create_agent_session(
        CreateAgentSessionOptions(
            cwd=options.cwd,
            credential_resolver=options.credential_resolver,
            model_runtime=runtime,
            session_manager=manager,
            thinking_level=thinking,
            no_tools=selection.no_tools,
            tool_names=selection.tool_names,
            exclude_tools=selection.exclude_tools,
        )
    )
    async with created:
        dispatcher = CommandDispatcher()
        reader_fn = read_line or _prompt_toolkit_reader()
        app_holder: list[InteractiveApp] = []
        controller_holder: list[ModelSettingsController] = []

        def rebuild() -> None:
            replay_width = terminal.columns
            if options.tui_mode != "fullscreen":
                replay_width = terminal.columns - 1
            previous_lines = tuple(app_holder[0].lines) if app_holder else ()
            history_lines = render_replay_lines(
                created.session.state.messages, max(1, replay_width)
            )
            initial_lines = history_lines if history_lines else previous_lines
            controller_holder[:] = [
                ModelSettingsController(
                    session=created.session,
                    model_runtime=runtime,
                    entry_id_factory=lambda: uuid4().hex,
                    timestamp_factory=lambda: datetime.now(UTC)
                    .isoformat(timespec="milliseconds")
                    .replace("+00:00", "Z"),
                )
            ]
            if options.tui_mode == "fullscreen":
                # Alt-screen viewport: repaint the clipped transcript every frame.
                app = InteractiveApp(
                    session=created.session,
                    dispatcher=dispatcher,
                    width=terminal.columns,
                    screen_sink=lambda lines: renderer.render(list(lines[-terminal.rows :])),
                    raw_sink=terminal.write,
                    compose_prompt=compose,
                    initial_lines=initial_lines,
                )
            else:
                # Inline mode: only the active block may repaint; settled blocks commit
                # so completed lines remain in terminal scrollback.
                app = InteractiveApp(
                    session=created.session,
                    dispatcher=dispatcher,
                    # Keep the cursor off the right margin. Windows terminals
                    # auto-wrap there, so the next live-tail clear would target
                    # the following row and leave the previous partial behind.
                    width=max(1, terminal.columns - 1),
                    block_sink=renderer.render,
                    commit_sink=renderer.commit,
                    raw_sink=terminal.write,
                    compose_prompt=compose,
                    initial_lines=initial_lines,
                )
            app_holder[:] = [app]

        def select_model(args: str) -> CommandOutcome:
            model_id = args.strip()
            if not model_id:
                current = created.session.state.model
                return CommandOutcome(
                    kind="message", text=f"current model: {current.provider}/{current.id}"
                )
            try:
                canonical = match_model_argument(runtime, model_id)
            except ValueError as error:
                return CommandOutcome(kind="error", text=str(error))
            controller_holder[0].apply(canonical, created.session.state.thinking_level)
            return CommandOutcome(kind="message", text=f"model: {canonical}")

        def select_thinking(args: str) -> CommandOutcome:
            level = args.strip()
            if not level:
                return CommandOutcome(
                    kind="message",
                    text=f"current thinking: {created.session.state.thinking_level}",
                )
            if level not in _THINKING_LEVEL_CHOICES:
                valid = ", ".join(_THINKING_LEVEL_CHOICES)
                return CommandOutcome(
                    kind="error", text=f"unknown thinking level: {level} (valid: {valid})"
                )
            controller_holder[0].apply(created.session.state.model.id, level)
            return CommandOutcome(kind="message", text=f"thinking: {level}")

        def copy_last_reply(_args: str) -> CommandOutcome:
            last = next(
                (
                    message
                    for message in reversed(created.session.state.messages)
                    if isinstance(message, AssistantMessage)
                ),
                None,
            )
            text = (
                "".join(
                    block.text for block in last.content if isinstance(block, TextContent)
                ).strip()
                if last is not None
                else ""
            )
            if not text:
                return CommandOutcome(kind="message", text="nothing to copy yet")
            payload = base64.b64encode(text.encode("utf-8")).decode("ascii")
            return CommandOutcome(kind="raw", text=f"\x1b]52;c;{payload}\x07")

        dispatcher.register(
            CommandSpec(
                name="help",
                source="builtin",
                handler=lambda _args: CommandOutcome(
                    kind="message",
                    text=(
                        "/help  show commands\n"
                        "/model [provider/model]  show or switch model (partial match ok)\n"
                        "/thinking [level]  show or set thinking level\n"
                        "/attach <path>  attach a file or image to the next prompt\n"
                        "/copy  copy the last reply to the terminal clipboard (OSC-52)\n"
                        "/compact  summarize the conversation so far into a checkpoint\n"
                        "/sessions  list saved sessions and switch by number\n"
                        "/fork  fork the current session and switch to the copy\n"
                        "/exit  leave the session\n"
                        "\n"
                        "keys: Esc/Ctrl+C cancels the running turn; a line typed during\n"
                        "a turn steers it; Ctrl+C while idle exits on the second press"
                    ),
                ),
            )
        )
        dispatcher.register(CommandSpec(name="model", source="builtin", handler=select_model))
        dispatcher.register(CommandSpec(name="thinking", source="builtin", handler=select_thinking))
        dispatcher.register(CommandSpec(name="copy", source="builtin", handler=copy_last_reply))

        async def compact_session(args: str) -> CommandOutcome:
            if args.strip():
                return CommandOutcome(kind="message", text="usage: /compact")
            if created.session.session_manager.leaf_id is None:
                return CommandOutcome(kind="message", text="nothing to compact yet")
            try:
                entry = await created.session.compact(reason="manual")
            except RuntimeError as error:
                return CommandOutcome(kind="error", text=str(error))
            except ValueError as error:
                return CommandOutcome(kind="error", text=f"cannot compact: {error}")
            return CommandOutcome(
                kind="message",
                text=f"compacted ({entry.tokens_before} tokens summarized into a checkpoint)",
            )

        dispatcher.register(CommandSpec(name="compact", source="builtin", handler=compact_session))

        pending_attachments: list[dict[str, JsonValue]] = []

        def attach_file(args: str) -> CommandOutcome:
            raw = args.strip().strip('"')
            if not raw:
                return CommandOutcome(kind="message", text="usage: /attach <path>")
            path = Path(raw)
            if not path.is_absolute():
                path = options.cwd / path
            model = created.model_runtime.model
            if classify_attachment(path) == "image":
                attachment = build_image_attachment(
                    path,
                    max_bytes=_MAX_IMAGE_BYTES,
                    image_supported=supports_image_input(model),
                )
            else:
                attachment = build_text_file_attachment(path)
            pending_attachments.append(attachment)
            name = str(attachment["name"])
            return CommandOutcome(
                kind="message", text=f"attached {name} ({len(pending_attachments)} pending)"
            )

        dispatcher.register(CommandSpec(name="attach", source="builtin", handler=attach_file))

        def _selector_directory() -> Path:
            if options.session_dir is not None:
                return options.session_dir
            return default_session_dir(options.cwd)

        async def open_session_selector(_args: str) -> CommandOutcome:
            directory = _selector_directory()
            catalog = await asyncio.to_thread(list_sessions, cwd=options.cwd, session_dir=directory)
            items: tuple[SessionSummary, ...] = catalog.sessions
            if not items:
                return CommandOutcome(kind="message", text=f"no saved sessions in {directory}")
            current_id = created.session.session_manager.header.id
            listing: list[str] = []
            for index, summary in enumerate(items, 1):
                marker = " (current)" if summary.id == current_id else ""
                label = summary.name or summary.id
                listing.append(f"{index}. {label} [{summary.id[:8]}]{marker}")
            app_holder[0].note("\n".join(listing))
            answer = await reader_fn("select › ")
            if answer is None or not answer.strip():
                return CommandOutcome(kind="message", text="session switch cancelled")
            try:
                chosen = int(answer.strip())
            except ValueError:
                return CommandOutcome(kind="error", text=f"not a number: {answer.strip()}")
            if not 1 <= chosen <= len(items):
                return CommandOutcome(kind="error", text=f"out of range 1..{len(items)}")
            summary = items[chosen - 1]
            await switch_to(created, summary)
            rebuild()
            app_holder[0].note(f"switched to {summary.id}")
            return CommandOutcome(kind="none")

        async def fork_current_session(_args: str) -> CommandOutcome:
            manager = created.session.session_manager
            if manager.path is None or manager.leaf_id is None:
                return CommandOutcome(
                    kind="error", text="cannot fork: the current session has no persisted turns"
                )
            summary = _PathRef(path=manager.path)
            await fork_from(created, summary)
            rebuild()
            app_holder[0].note(f"forked to {created.session.session_manager.header.id}")
            return CommandOutcome(kind="none")

        def compose(line: str) -> AgentMessage | str:
            if not pending_attachments:
                return line
            attachments = tuple(pending_attachments)
            pending_attachments.clear()
            blocks: list[TextContent | ImageContent] = [TextContent(text=line)]
            for attachment in attachments:
                if attachment.get("type") == "image":
                    blocks.append(
                        ImageContent(
                            data=str(attachment["data"]),
                            mime_type=str(attachment["mimeType"]),
                        )
                    )
                else:
                    blocks.append(
                        TextContent(
                            text=f"[attached file {attachment['name']}]\n{attachment['content']}"
                        )
                    )
            return UserMessage(content=tuple(blocks), timestamp=_message_timestamp())

        dispatcher.register(
            CommandSpec(name="sessions", source="builtin", handler=open_session_selector)
        )
        dispatcher.register(
            CommandSpec(name="fork", source="builtin", handler=fork_current_session)
        )
        extensions = created.services.extensions
        if isinstance(extensions, _HasRegistry):
            skipped = dispatcher.register_registry(extensions.registry)
            if skipped:
                names = ", ".join(f"/{name}" for name in skipped)
                stderr.write(
                    f"skipped extension commands already provided by the product: {names}\n"
                )
                stderr.flush()
        fullscreen = options.tui_mode == "fullscreen"
        terminal = _StreamTerminal(stdout, fullscreen=fullscreen)
        renderer = ScreenRenderer(terminal) if fullscreen else InlineRenderer(terminal)
        rebuild()
        terminal.start()
        char_reader = read_char if read_char is not None else _console_char_reader()
        try:
            last_idle_interrupt: float | None = None
            while True:
                try:
                    line = await reader_fn("› ")
                except KeyboardInterrupt:
                    # First press clears the input and hints; a second press
                    # within two seconds exits. Esc cancels a running turn.
                    stdout.write("\n")
                    now = time.monotonic()
                    if last_idle_interrupt is not None and now - last_idle_interrupt <= 2.0:
                        return 130
                    last_idle_interrupt = now
                    stdout.write("press Ctrl+C again to exit (Esc cancels a running turn)\n")
                    continue
                last_idle_interrupt = None
                if line is None or line.strip() in {"/exit", "/quit"}:
                    return 0
                if not line.strip():
                    continue
                try:
                    await _drive_turn(app_holder[0], created.session, line, char_reader)
                except Exception as error:
                    stderr.write(f"{error}\n")
                    stderr.flush()
        finally:
            terminal.stop()


__all__ = ["InteractiveOptions", "ReadLine", "run_interactive"]
