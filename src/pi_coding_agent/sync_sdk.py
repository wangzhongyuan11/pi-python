"""Synchronous convenience wrapper for callers without an event loop."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import Self

from pi_agent import AgentMessage

from .agent_session import AgentSession
from .sdk import CreateAgentSessionOptions, CreatedAgentSession, create_agent_session


class SyncSdkEventLoopError(RuntimeError):
    pass


def _run[ResultT](operation: Callable[[], Awaitable[ResultT]]) -> ResultT:
    try:
        asyncio.get_running_loop()
    except RuntimeError:

        async def invoke() -> ResultT:
            return await operation()

        return asyncio.run(invoke())
    raise SyncSdkEventLoopError(
        "synchronous SDK cannot run inside an active event loop; use the async SDK"
    )


class SyncCreatedAgentSession:
    __slots__ = ("_created", "_closed")

    def __init__(self, created: CreatedAgentSession) -> None:
        self._created = created
        self._closed = False

    @property
    def session(self) -> AgentSession:
        return self._created.session

    @property
    def is_closed(self) -> bool:
        return self._closed

    def prompt(self, prompt: str | AgentMessage | Sequence[AgentMessage]) -> None:
        _run(lambda: self.session.prompt(prompt))

    def wait_for_idle(self) -> None:
        _run(self.session.wait_for_idle)

    def close(self) -> None:
        if self._closed:
            return
        _run(self._created.close)
        self._closed = True

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: object,
    ) -> None:
        del exception_type, exception, traceback
        self.close()


def create_agent_session_sync(
    options: CreateAgentSessionOptions | None = None,
) -> SyncCreatedAgentSession:
    return SyncCreatedAgentSession(_run(lambda: create_agent_session(options)))


__all__ = [
    "SyncCreatedAgentSession",
    "SyncSdkEventLoopError",
    "create_agent_session_sync",
]
