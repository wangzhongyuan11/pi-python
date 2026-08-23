"""Session lifecycle owner that rebuilds every cwd-bound runtime component."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from .session.manager import SessionManager
from .session.recovery import recover_unmatched_tool_calls

type RuntimeReason = Literal["initial", "new", "resume", "fork", "switch", "quit"]


class AgentSessionRuntimeError(RuntimeError):
    pass


class RuntimeSession(Protocol):
    async def close(self, reason: RuntimeReason) -> None: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class RuntimeTarget:
    cwd: Path
    session_manager: SessionManager
    reason: RuntimeReason
    generation: int


@dataclass(frozen=True, slots=True, kw_only=True)
class RuntimeComponents[SessionT: RuntimeSession, ServicesT]:
    session: SessionT
    services: ServicesT


type RuntimeFactory[SessionT: RuntimeSession, ServicesT] = Callable[
    [RuntimeTarget], Awaitable[RuntimeComponents[SessionT, ServicesT]]
]


@dataclass(frozen=True, slots=True, kw_only=True)
class _Binding[SessionT: RuntimeSession, ServicesT]:
    target: RuntimeTarget
    components: RuntimeComponents[SessionT, ServicesT]


class AgentSessionRuntime[SessionT: RuntimeSession, ServicesT]:
    __slots__ = ("_binding", "_closed", "_factory")

    def __init__(
        self,
        factory: RuntimeFactory[SessionT, ServicesT],
        binding: _Binding[SessionT, ServicesT],
    ) -> None:
        self._factory = factory
        self._binding = binding
        self._closed = False

    @classmethod
    async def create(
        cls,
        factory: RuntimeFactory[SessionT, ServicesT],
        *,
        cwd: Path,
        session_manager: SessionManager,
    ) -> AgentSessionRuntime[SessionT, ServicesT]:
        target = RuntimeTarget(
            cwd=cwd.resolve(),
            session_manager=session_manager,
            reason="initial",
            generation=0,
        )
        recover_unmatched_tool_calls(session_manager)
        components = await factory(target)
        return cls(factory, _Binding(target=target, components=components))

    @property
    def session(self) -> SessionT:
        self._ensure_open()
        return self._binding.components.session

    @property
    def services(self) -> ServicesT:
        self._ensure_open()
        return self._binding.components.services

    @property
    def session_manager(self) -> SessionManager:
        self._ensure_open()
        return self._binding.target.session_manager

    @property
    def cwd(self) -> Path:
        self._ensure_open()
        return self._binding.target.cwd

    @property
    def generation(self) -> int:
        self._ensure_open()
        return self._binding.target.generation

    async def new_session(self, session_manager: SessionManager) -> None:
        manager_cwd = Path(session_manager.header.cwd).resolve()
        if manager_cwd != self.cwd:
            raise AgentSessionRuntimeError(
                f"new session cwd {manager_cwd} does not match current cwd {self.cwd}"
            )
        await self._replace("new", session_manager, self.cwd)

    async def resume(
        self,
        session_manager: SessionManager,
        *,
        cwd_override: Path | None = None,
    ) -> None:
        cwd = (
            Path(session_manager.header.cwd).resolve()
            if cwd_override is None
            else cwd_override.resolve()
        )
        await self._replace("resume", session_manager, cwd)

    async def fork(self, session_manager: SessionManager) -> None:
        await self._replace("fork", session_manager, Path(session_manager.header.cwd).resolve())

    async def switch(self, session_manager: SessionManager) -> None:
        await self._replace("switch", session_manager, Path(session_manager.header.cwd).resolve())

    async def _replace(
        self,
        reason: Literal["new", "resume", "fork", "switch"],
        session_manager: SessionManager,
        cwd: Path,
    ) -> None:
        self._ensure_open()
        generation = self._binding.target.generation + 1
        await self._binding.components.session.close(reason)
        target = RuntimeTarget(
            cwd=cwd.resolve(),
            session_manager=session_manager,
            reason=reason,
            generation=generation,
        )
        try:
            recover_unmatched_tool_calls(session_manager)
            components = await self._factory(target)
        except BaseException:
            self._closed = True
            raise
        self._binding = _Binding(target=target, components=components)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._binding.components.session.close("quit")

    def _ensure_open(self) -> None:
        if self._closed:
            raise AgentSessionRuntimeError("AgentSessionRuntime is closed")


__all__ = [
    "AgentSessionRuntime",
    "AgentSessionRuntimeError",
    "RuntimeComponents",
    "RuntimeFactory",
    "RuntimeReason",
    "RuntimeSession",
    "RuntimeTarget",
]
