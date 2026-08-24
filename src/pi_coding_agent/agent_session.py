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

from .agent_session_events import (
    AgentSessionEvent,
    AgentSessionEventListener,
    AutoRetryEndEvent,
    AutoRetryStartEvent,
    EntryAppendedEvent,
)
from .agent_session_runtime import RuntimeReason
from .context_overflow import OverflowRecovery, is_context_overflow
from .retry import RetryPolicy, Sleep, is_retryable_assistant_error
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
        "_overflow_recovery",
        "_retry_cancel",
        "_retry_policy",
        "_sleep",
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
        retry_policy: RetryPolicy | None = None,
        sleep: Sleep = asyncio.sleep,
        overflow_recovery: OverflowRecovery | None = None,
    ) -> None:
        self.agent = agent
        self.session_manager = session_manager
        self.services = services
        self._entry_id_factory = entry_id_factory
        self._timestamp_factory = timestamp_factory
        self._on_close = on_close
        self._retry_policy = retry_policy or RetryPolicy()
        self._sleep = sleep
        self._retry_cancel = asyncio.Event()
        self._overflow_recovery = overflow_recovery
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
        baseline = self.agent.state.messages
        next_prompt: str | AgentMessage | Sequence[AgentMessage] = prompt
        self._retry_cancel = asyncio.Event()
        attempt = 0
        overflow_attempted = False
        while True:
            await self.agent.prompt(next_prompt)
            last = self.agent.state.messages[-1] if self.agent.state.messages else None
            if (
                isinstance(last, AssistantMessage)
                and is_context_overflow(last)
                and self._overflow_recovery is not None
                and not overflow_attempted
            ):
                overflow_attempted = True
                self.agent.restore_messages(baseline)
                if await self._overflow_recovery():
                    continue
                return
            error = self._retryable_error()
            if error is None:
                if attempt:
                    await self._emit(
                        AutoRetryEndEvent(success=True, attempt=attempt), asyncio.Event()
                    )
                return
            if (
                not self._retry_policy.allows_turn_retry
                or attempt >= self._retry_policy.max_retries
                or self._retry_cancel.is_set()
            ):
                if attempt:
                    await self._emit(
                        AutoRetryEndEvent(success=False, attempt=attempt, final_error=error),
                        asyncio.Event(),
                    )
                return
            attempt += 1
            delay = self._retry_policy.delay(attempt)
            await self._emit(
                AutoRetryStartEvent(
                    attempt=attempt,
                    max_attempts=self._retry_policy.max_retries,
                    delay_seconds=delay,
                    error_message=error,
                ),
                asyncio.Event(),
            )
            if await self._wait_for_retry(delay):
                await self._emit(
                    AutoRetryEndEvent(
                        success=False, attempt=attempt, final_error="retry cancelled"
                    ),
                    asyncio.Event(),
                )
                return
            self.agent.restore_messages(self.agent.state.messages[:-1])
            next_prompt = ()

    def cancel_retry(self) -> None:
        self._retry_cancel.set()

    def abort(self) -> None:
        self.cancel_retry()
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

    def _retryable_error(self) -> str | None:
        if not self.agent.state.messages:
            return None
        message = self.agent.state.messages[-1]
        if not isinstance(message, AssistantMessage) or not is_retryable_assistant_error(message):
            return None
        return message.error_message or "provider turn failed"

    async def _wait_for_retry(self, delay: float) -> bool:
        async def sleep_once() -> None:
            await self._sleep(delay)

        async def wait_for_cancel() -> None:
            await self._retry_cancel.wait()

        sleep_task = asyncio.create_task(sleep_once())
        cancel_task = asyncio.create_task(wait_for_cancel())
        try:
            done, _pending = await asyncio.wait(
                (sleep_task, cancel_task), return_when=asyncio.FIRST_COMPLETED
            )
            if cancel_task in done:
                return True
            await sleep_task
            return False
        finally:
            for task in (sleep_task, cancel_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(sleep_task, cancel_task, return_exceptions=True)


__all__ = ["AgentSession", "AgentSessionClosedError"]
