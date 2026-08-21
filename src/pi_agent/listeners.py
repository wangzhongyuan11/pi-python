"""Ordered lifecycle listener dispatch for an active agent run."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable

from .events import AgentEvent

type AgentEventListener = Callable[[AgentEvent, asyncio.Event], None | Awaitable[None]]


class AgentListenerRegistry:
    """Await sync and async listeners in subscription order."""

    __slots__ = ("_listeners", "_pending")

    def __init__(self) -> None:
        self._listeners: list[AgentEventListener] = []
        self._pending: set[asyncio.Future[None]] = set()

    def subscribe(self, listener: AgentEventListener) -> Callable[[], None]:
        if listener not in self._listeners:
            self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    async def emit(self, event: AgentEvent, signal: asyncio.Event) -> None:
        for listener in tuple(self._listeners):
            result = listener(event, signal)
            if not inspect.isawaitable(result):
                continue
            pending = asyncio.ensure_future(result)
            self._pending.add(pending)
            try:
                await pending
            finally:
                self._pending.discard(pending)

    async def wait_for_pending(self) -> None:
        while self._pending:
            await asyncio.gather(*tuple(self._pending))


__all__ = ["AgentEventListener", "AgentListenerRegistry"]
