"""Late-bound actions captured by an extension during activation."""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pi_agent import AgentTool, CustomMessage
from pi_ai import (
    JsonObject,
    JsonValue,
    Model,
    ModelThinkingLevel,
    TextContent,
    UserMessage,
    clamp_thinking_level,
)

from ..session.models import SessionInfoEntry

if TYPE_CHECKING:
    from ..agent_session import AgentSession
    from ..model_runtime import ModelRuntime


class ExtensionContextUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ExtensionCommandInfo:
    name: str
    source: str


@dataclass(frozen=True, slots=True)
class ExtensionContextUsage:
    tokens: int
    context_window: int
    percent: float


@dataclass(frozen=True, slots=True)
class ExtensionExecResult:
    stdout: str
    stderr: str
    code: int
    killed: bool


@dataclass(frozen=True, slots=True)
class ExtensionToolInfo:
    name: str
    description: str
    parameters: JsonObject
    source: str


@dataclass(slots=True)
class _Binding:
    session: AgentSession
    model_runtime: ModelRuntime
    all_tools: tuple[AgentTool[Any, Any], ...]
    tool_sources: dict[str, str]
    commands: tuple[ExtensionCommandInfo, ...]
    project_trusted: bool


class ExtensionActions:
    """Controlled session actions whose binding changes with the runtime generation."""

    __slots__ = ("_binding", "_exec_processes", "_shutdown_requested")

    def __init__(self) -> None:
        self._binding: _Binding | None = None
        self._exec_processes: set[asyncio.subprocess.Process] = set()
        self._shutdown_requested = False

    def bind(
        self,
        *,
        session: AgentSession,
        model_runtime: ModelRuntime,
        all_tools: tuple[AgentTool[Any, Any], ...],
        tool_sources: dict[str, str] | None = None,
        commands: tuple[ExtensionCommandInfo, ...] = (),
        project_trusted: bool = False,
    ) -> None:
        self._binding = _Binding(
            session,
            model_runtime,
            all_tools,
            dict(tool_sources or {}),
            commands,
            project_trusted,
        )
        self._shutdown_requested = False

    def invalidate(self) -> None:
        self._binding = None

    def append_entry(self, custom_type: str, data: JsonValue = None) -> str:
        return self._require().session.append_custom_entry(custom_type, data)

    def send_message(
        self,
        custom_type: str,
        content: str,
        *,
        display: bool = True,
        details: JsonValue = None,
        trigger_turn: bool = False,
        deliver_as: Literal["steer", "follow_up"] = "follow_up",
    ) -> asyncio.Task[None] | str:
        binding = self._require()
        if not trigger_turn:
            return binding.session.append_custom_message(
                custom_type, content, display=display, details=details
            )
        binding.session.append_custom_message(
            custom_type, content, display=display, details=details
        )
        message = CustomMessage(
            custom_type=custom_type,
            content=content,
            display=display,
            details=details,
            timestamp=time.time_ns() // 1_000_000,
        )
        if binding.session.state.is_streaming:
            queue = (
                binding.session.agent.steer
                if deliver_as == "steer"
                else binding.session.agent.follow_up
            )
            queue(message)
            return asyncio.create_task(_completed())
        return asyncio.create_task(binding.session.prompt(()))

    def send_user_message(
        self,
        content: str,
        *,
        deliver_as: Literal["steer", "follow_up"] = "follow_up",
    ) -> asyncio.Task[None]:
        binding = self._require()
        message = UserMessage(
            content=(TextContent(text=content),), timestamp=time.time_ns() // 1_000_000
        )
        if binding.session.state.is_streaming:
            queue = (
                binding.session.agent.steer
                if deliver_as == "steer"
                else binding.session.agent.follow_up
            )
            queue(message)
            return asyncio.create_task(_completed())
        return asyncio.create_task(binding.session.prompt(message))

    def set_session_name(self, name: str) -> str:
        return self._require().session.set_session_name(name)

    def get_session_name(self) -> str | None:
        entries = self._require().session.session_manager.entries
        return next(
            (entry.name for entry in reversed(entries) if isinstance(entry, SessionInfoEntry)),
            None,
        )

    def set_label(self, entry_id: str, label: str | None) -> str:
        return self._require().session.set_label(entry_id, label)

    async def exec(
        self,
        command: str,
        args: tuple[str, ...] | list[str] = (),
        *,
        cwd: str | Path | None = None,
        timeout: float | None = None,
    ) -> ExtensionExecResult:
        binding = self._require()
        working_directory = binding.session.services.cwd if cwd is None else Path(cwd).resolve()
        return await _exec_command(
            command,
            tuple(args),
            cwd=working_directory,
            timeout=timeout,
            processes=self._exec_processes,
        )

    def terminate_exec_processes(self) -> None:
        """Kill every in-flight exec child so reload/exit leaves no orphans."""

        for process in tuple(self._exec_processes):
            if process.returncode is None:
                process.kill()
        self._exec_processes.clear()

    def get_active_tools(self) -> tuple[str, ...]:
        return tuple(tool.name for tool in self._require().session.state.tools)

    def get_all_tools(self) -> tuple[ExtensionToolInfo, ...]:
        binding = self._require()
        return tuple(
            ExtensionToolInfo(
                name=tool.name,
                description=tool.description,
                parameters=tool.parameters,
                source=binding.tool_sources.get(tool.name, "builtin"),
            )
            for tool in binding.all_tools
        )

    def get_commands(self) -> tuple[ExtensionCommandInfo, ...]:
        return self._require().commands

    def set_active_tools(self, names: tuple[str, ...] | list[str]) -> None:
        self._require().session.agent.set_active_tool_names(names)

    def set_model(self, model: str) -> bool:
        binding = self._require()
        provider, separator, model_id = model.partition("/")
        selected = binding.model_runtime.select_model(
            model_id if separator else provider,
            provider_id=provider if separator else None,
        )
        binding.session.set_model(selected)
        return True

    def get_thinking_level(self) -> ModelThinkingLevel:
        return self._require().session.state.thinking_level

    def set_thinking_level(self, level: ModelThinkingLevel) -> None:
        binding = self._require()
        binding.session.set_thinking_level(clamp_thinking_level(binding.session.state.model, level))

    @property
    def cwd(self) -> Path:
        return self._require().session.services.cwd

    @property
    def model(self) -> Model:
        return self._require().session.state.model

    def is_idle(self) -> bool:
        return not self._require().session.state.is_streaming

    def is_project_trusted(self) -> bool:
        return self._require().project_trusted

    @property
    def signal(self) -> asyncio.Event | None:
        return self._require().session.agent.signal

    def abort(self) -> None:
        self._require().session.abort()

    def has_pending_messages(self) -> bool:
        return self._require().session.agent.has_queued_messages

    def shutdown(self) -> None:
        self._require().session.abort()
        self._shutdown_requested = True

    @property
    def shutdown_requested(self) -> bool:
        self._require()
        return self._shutdown_requested

    def get_context_usage(self) -> ExtensionContextUsage:
        session = self._require().session
        context_window = session.state.model.context_window
        characters = sum(len(repr(message)) for message in session.messages)
        tokens = math.ceil(characters / 4)
        return ExtensionContextUsage(
            tokens=tokens,
            context_window=context_window,
            percent=(tokens / context_window) * 100,
        )

    def compact(self) -> asyncio.Task[object]:
        session = self._require().session
        return asyncio.create_task(session.compact())

    def get_system_prompt(self) -> str:
        return self._require().session.state.system_prompt

    def _require(self) -> _Binding:
        if self._binding is None:
            raise ExtensionContextUnavailableError("extension session context is not active")
        return self._binding


class ExtensionCommandContext:
    """Command-only session replacement actions guarded by one action generation."""

    __slots__ = (
        "_actions",
        "_fork",
        "_navigate",
        "_new_session",
        "_reload",
        "_switch",
        "_wait_for_idle",
    )

    def __init__(self, actions: ExtensionActions) -> None:
        self._actions = actions
        self._wait_for_idle: Callable[[], Awaitable[None]] = _completed
        self._new_session: Callable[[], Awaitable[bool]] = _false
        self._fork: Callable[[str], Awaitable[bool]] = _false_with_argument
        self._navigate: Callable[[str], Awaitable[bool]] = _false_with_argument
        self._switch: Callable[[str], Awaitable[bool]] = _false_with_argument
        self._reload: Callable[[], Awaitable[None]] = _completed

    def bind(
        self,
        *,
        wait_for_idle: Callable[[], Awaitable[None]],
        new_session: Callable[[], Awaitable[bool]],
        fork: Callable[[str], Awaitable[bool]],
        navigate: Callable[[str], Awaitable[bool]],
        switch: Callable[[str], Awaitable[bool]],
        reload: Callable[[], Awaitable[None]],
    ) -> None:
        self._wait_for_idle = wait_for_idle
        self._new_session = new_session
        self._fork = fork
        self._navigate = navigate
        self._switch = switch
        self._reload = reload

    def __getattr__(self, name: str) -> object:
        if name.startswith("_"):
            raise AttributeError(name)
        self._ensure_active()
        return getattr(self._actions, name)

    async def wait_for_idle(self) -> None:
        self._ensure_active()
        await self._wait_for_idle()

    async def new_session(self) -> bool:
        self._ensure_active()
        return await self._new_session()

    async def fork(self, entry_id: str) -> bool:
        self._ensure_active()
        return await self._fork(entry_id)

    async def navigate_tree(self, target_id: str) -> bool:
        self._ensure_active()
        return await self._navigate(target_id)

    async def switch_session(self, session_path: str) -> bool:
        self._ensure_active()
        return await self._switch(session_path)

    async def reload(self) -> None:
        self._ensure_active()
        await self._reload()

    def _ensure_active(self) -> None:
        self._actions.is_idle()


async def _completed() -> None:
    return None


async def _false() -> bool:
    return False


async def _false_with_argument(_value: str) -> bool:
    return False


async def _exec_command(
    command: str,
    args: tuple[str, ...],
    *,
    cwd: Path,
    timeout: float | None,
    processes: set[asyncio.subprocess.Process] | None = None,
) -> ExtensionExecResult:
    if not command:
        raise ValueError("extension command must not be empty")
    if timeout is not None and timeout <= 0:
        raise ValueError("extension command timeout must be positive")
    process = await asyncio.create_subprocess_exec(
        command,
        *args,
        cwd=cwd,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    if processes is not None:
        processes.add(process)
    killed = False
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError:
        killed = True
        process.kill()
        stdout, stderr = await process.communicate()
    finally:
        if processes is not None:
            processes.discard(process)
    return ExtensionExecResult(
        stdout=stdout.decode(errors="replace"),
        stderr=stderr.decode(errors="replace"),
        code=process.returncode if process.returncode is not None else 1,
        killed=killed,
    )


__all__ = [
    "ExtensionActions",
    "ExtensionCommandInfo",
    "ExtensionCommandContext",
    "ExtensionContextUnavailableError",
    "ExtensionContextUsage",
    "ExtensionExecResult",
    "ExtensionToolInfo",
]
