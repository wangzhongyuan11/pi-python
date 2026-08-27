"""Real interactive process loop built on the shared SDK and product TUI."""

from __future__ import annotations

import asyncio
import base64
import shutil
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol, TextIO, runtime_checkable
from uuid import uuid4

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

from ..attachments import (
    build_image_attachment,
    build_text_file_attachment,
    classify_attachment,
    supports_image_input,
)
from ..cli.run import HeadlessOptions, resolve_session_manager
from ..extensions.registry import CapabilityRegistry
from ..model_runtime import ModelRuntime, create_model_runtime
from ..sdk import CreateAgentSessionOptions, create_agent_session, default_session_dir
from ..session.catalog import SessionSummary, list_sessions
from .commands import CommandDispatcher, CommandOutcome, CommandSpec
from .config_ui import ModelSettingsController
from .main import InteractiveApp
from .session_ui import fork_from, switch_to

type ReadLine = Callable[[str], Awaitable[str | None]]

_MAX_IMAGE_BYTES = 10 * 1024 * 1024


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


class _StreamTerminal:
    __slots__ = ("_fullscreen", "_output")

    def __init__(self, output: TextIO, *, fullscreen: bool) -> None:
        self._output = output
        self._fullscreen = fullscreen

    @property
    def columns(self) -> int:
        return max(1, shutil.get_terminal_size(fallback=(80, 24)).columns)

    @property
    def rows(self) -> int:
        return max(1, shutil.get_terminal_size(fallback=(80, 24)).lines)

    def write(self, data: str) -> None:
        self._output.write(data)
        self._output.flush()

    def move_by(self, lines: int) -> None:
        if lines < 0:
            self.write(f"\x1b[{-lines}A")
        elif lines > 0:
            self.write(f"\x1b[{lines}B")

    def clear_line(self) -> None:
        self.write("\r\x1b[K")

    def clear_screen(self) -> None:
        if self._fullscreen:
            self.write("\x1b[2J\x1b[H")

    def start(self) -> None:
        if self._fullscreen:
            self.write("\x1b[?1049h")

    def stop(self) -> None:
        if self._fullscreen:
            self.write("\x1b[?1049l")


def _prompt_toolkit_reader() -> ReadLine:
    from prompt_toolkit import PromptSession

    session: PromptSession[str] = PromptSession()

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
            session_dir=options.session_dir,
            model_runtime=runtime,
        )
    )
    created = await create_agent_session(
        CreateAgentSessionOptions(
            cwd=options.cwd,
            credential_resolver=options.credential_resolver,
            model_runtime=runtime,
            session_manager=manager,
            thinking_level=thinking,
        )
    )
    async with created:
        dispatcher = CommandDispatcher()
        reader_fn = read_line or _prompt_toolkit_reader()
        app_holder: list[InteractiveApp] = []
        controller_holder: list[ModelSettingsController] = []

        def rebuild() -> None:
            previous_lines = tuple(app_holder[0].lines) if app_holder else ()
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
                    initial_lines=previous_lines,
                )
            else:
                # Inline mode: only the active block may repaint; settled blocks commit
                # so completed lines remain in terminal scrollback.
                app = InteractiveApp(
                    session=created.session,
                    dispatcher=dispatcher,
                    width=terminal.columns,
                    block_sink=renderer.render,
                    commit_sink=renderer.commit,
                    raw_sink=terminal.write,
                    compose_prompt=compose,
                    initial_lines=previous_lines,
                )
            app_holder[:] = [app]

        def select_model(args: str) -> CommandOutcome:
            model_id = args.strip()
            if not model_id:
                return CommandOutcome(
                    kind="message", text=f"current model: {created.session.state.model.id}"
                )
            controller_holder[0].apply(model_id, created.session.state.thinking_level)
            return CommandOutcome(kind="message", text=f"model: {model_id}")

        def select_thinking(args: str) -> CommandOutcome:
            level = args.strip()
            if not level:
                return CommandOutcome(
                    kind="message",
                    text=f"current thinking: {created.session.state.thinking_level}",
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
                        "/model [provider/model]  show or switch model\n"
                        "/thinking [level]  show or set thinking level\n"
                        "/attach <path>  attach a file or image to the next prompt\n"
                        "/copy  copy the last reply to the terminal clipboard (OSC-52)\n"
                        "/sessions  list saved sessions and switch by number\n"
                        "/fork  fork the current session and switch to the copy\n"
                        "/exit  leave the session"
                    ),
                ),
            )
        )
        dispatcher.register(CommandSpec(name="model", source="builtin", handler=select_model))
        dispatcher.register(CommandSpec(name="thinking", source="builtin", handler=select_thinking))
        dispatcher.register(CommandSpec(name="copy", source="builtin", handler=copy_last_reply))

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
        try:
            while True:
                try:
                    line = await reader_fn("› ")
                except KeyboardInterrupt:
                    stdout.write("\n")
                    return 130
                if line is None or line.strip() in {"/exit", "/quit"}:
                    return 0
                if not line.strip():
                    continue
                try:
                    await app_holder[0].handle(line)
                except Exception as error:
                    stderr.write(f"{error}\n")
                    stderr.flush()
        finally:
            terminal.stop()


__all__ = ["InteractiveOptions", "ReadLine", "run_interactive"]
