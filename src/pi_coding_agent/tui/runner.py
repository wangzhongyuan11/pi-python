"""Real interactive process loop built on the shared SDK and product TUI."""

from __future__ import annotations

import shutil
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol, TextIO, runtime_checkable
from uuid import uuid4

from pi_ai import CredentialResolver, ModelThinkingLevel, clamp_thinking_level
from pi_tui.render import ScreenRenderer

from ..cli.run import HeadlessOptions, resolve_session_manager
from ..extensions.registry import CapabilityRegistry
from ..model_runtime import ModelRuntime, create_model_runtime
from ..sdk import CreateAgentSessionOptions, create_agent_session
from .commands import CommandDispatcher, CommandOutcome, CommandSpec
from .config_ui import ModelSettingsController
from .main import InteractiveApp

type ReadLine = Callable[[str], Awaitable[str | None]]


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
        controller = ModelSettingsController(
            session=created.session,
            model_runtime=runtime,
            entry_id_factory=lambda: uuid4().hex,
            timestamp_factory=lambda: datetime.now(UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
        )

        def select_model(args: str) -> CommandOutcome:
            model_id = args.strip()
            if not model_id:
                return CommandOutcome(
                    kind="message", text=f"current model: {created.session.state.model.id}"
                )
            controller.apply(model_id, created.session.state.thinking_level)
            return CommandOutcome(kind="message", text=f"model: {model_id}")

        def select_thinking(args: str) -> CommandOutcome:
            level = args.strip()
            if not level:
                return CommandOutcome(
                    kind="message",
                    text=f"current thinking: {created.session.state.thinking_level}",
                )
            controller.apply(created.session.state.model.id, level)
            return CommandOutcome(kind="message", text=f"thinking: {level}")

        dispatcher.register(
            CommandSpec(
                name="help",
                source="builtin",
                handler=lambda _args: CommandOutcome(
                    kind="message", text="/help  show commands\n/exit  leave the session"
                ),
            )
        )
        dispatcher.register(CommandSpec(name="model", source="builtin", handler=select_model))
        dispatcher.register(CommandSpec(name="thinking", source="builtin", handler=select_thinking))
        extensions = created.services.extensions
        if isinstance(extensions, _HasRegistry):
            dispatcher.register_registry(extensions.registry)
        fullscreen = options.tui_mode == "fullscreen"
        terminal = _StreamTerminal(stdout, fullscreen=fullscreen)
        renderer = ScreenRenderer(terminal)
        app = InteractiveApp(
            session=created.session,
            dispatcher=dispatcher,
            width=terminal.columns,
            screen_sink=lambda lines: renderer.render(
                list(lines[-terminal.rows :]) if fullscreen else list(lines)
            ),
        )
        reader = read_line or _prompt_toolkit_reader()
        terminal.start()
        try:
            while True:
                try:
                    line = await reader("› ")
                except KeyboardInterrupt:
                    stdout.write("\n")
                    return 130
                if line is None or line.strip() in {"/exit", "/quit"}:
                    return 0
                if not line.strip():
                    continue
                try:
                    await app.handle(line)
                except Exception as error:
                    stderr.write(f"{error}\n")
                    stderr.flush()
        finally:
            terminal.stop()


__all__ = ["InteractiveOptions", "ReadLine", "run_interactive"]
