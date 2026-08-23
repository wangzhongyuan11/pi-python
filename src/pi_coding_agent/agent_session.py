"""Product facade that owns one Agent and its stable service ports."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from uuid import uuid4

from pi_agent import (
    Agent,
    AgentEvent,
    AgentMessage,
    AgentState,
    MessageEndEvent,
)
from pi_ai import AssistantMessage, ToolResultMessage, UserMessage
from pi_ai.wire.messages import dump_message

from .agent_session_events import AgentSessionEvent, AgentSessionEventListener, EntryAppendedEvent
from .agent_session_runtime import RuntimeReason
from .services import ProductServices
from .session.manager import SessionManager
from .session.models import MessageEntry


def _entry_id() -> str:
    return uuid4().hex


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class AgentSessionClosedError(RuntimeError):
    pass


class AgentSession:
    __slots__ = (
        "_closed",
        "_entry_id_factory",
        "_listeners",
        "_on_close",
        "_timestamp_factory",
        "_unsubscribe_agent",
        "agent",
        "services",
        "session_manager",
    )

    def __init__(
        self,
        *,
        agent: Agent,
        session_manager: SessionManager,
        services: ProductServices,
        entry_id_factory: Callable[[], str] = _entry_id,
        timestamp_factory: Callable[[], str] = _timestamp,
        on_close: Callable[[RuntimeReason], None] | None = None,
    ) -> None:
        self.agent = agent
        self.session_manager = session_manager
        self.services = services
        self._entry_id_factory = entry_id_factory
        self._timestamp_factory = timestamp_factory
        self._on_close = on_close
        self._listeners: list[AgentSessionEventListener] = []
        self._closed = False
        self._unsubscribe_agent = agent.subscribe(self._handle_agent_event)

    @property
    def state(self) -> AgentState:
        return self.agent.state

    @property
    def messages(self) -> tuple[AgentMessage, ...]:
        return self.agent.state.messages

    @property
    def is_closed(self) -> bool:
        return self._closed

    def subscribe(self, listener: AgentSessionEventListener) -> Callable[[], None]:
        self._ensure_open()
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    async def prompt(self, prompt: str | AgentMessage | Sequence[AgentMessage]) -> None:
        self._ensure_open()
        await self.agent.prompt(prompt)

    def abort(self) -> None:
        self.agent.abort()

    async def wait_for_idle(self) -> None:
        await self.agent.wait_for_idle()
        return None

    async def close(self, reason: RuntimeReason) -> None:
        if self._closed:
            return
        self._closed = True
        self.agent.abort()
        await self.agent.wait_for_idle()
        self._unsubscribe_agent()
        if self._on_close is not None:
            self._on_close(reason)

    async def _handle_agent_event(self, event: AgentEvent, signal: asyncio.Event) -> None:
        entry: MessageEntry | None = None
        if isinstance(event, MessageEndEvent):
            entry = self._persist_message(event)
        await self._emit(event, signal)
        if entry is not None:
            await self._emit(EntryAppendedEvent(entry=entry), signal)

    async def _emit(self, event: AgentSessionEvent, signal: asyncio.Event) -> None:
        for listener in tuple(self._listeners):
            result = listener(event, signal)
            if inspect.isawaitable(result):
                await result

    def _persist_message(self, event: MessageEndEvent) -> MessageEntry | None:
        message = event.message
        if not isinstance(message, UserMessage | AssistantMessage | ToolResultMessage):
            return None
        entry = MessageEntry(
            type="message",
            id=self._entry_id_factory(),
            parent_id=self.session_manager.leaf_id,
            timestamp=self._timestamp_factory(),
            message=dump_message(message),
        )
        self.session_manager.append(entry)
        return entry

    def _ensure_open(self) -> None:
        if self._closed:
            raise AgentSessionClosedError("AgentSession is closed")


__all__ = ["AgentSession", "AgentSessionClosedError"]
