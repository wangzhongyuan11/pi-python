"""Interactive product TUI integration: input, events, and rendering."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import Callable

from pi_agent import (
    MessageEndEvent,
    MessageStartEvent,
    MessageUpdateEvent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
    ToolExecutionUpdateEvent,
)
from pi_ai import AssistantMessage, TextContent, ThinkingContent
from pi_tui.layout import wrap_text
from pi_tui.width import visible_width

from ..agent_session import AgentSession
from ..agent_session_events import AutoRetryEndEvent, AutoRetryStartEvent
from .commands import CommandDispatcher
from .render_messages import AssistantMessageView
from .render_status import RetryStatusLine
from .render_tools import ToolExecutionView


def _pad(line: str, width: int) -> str:
    return line + " " * max(0, width - visible_width(line))


class InteractiveApp:
    """Drives one AgentSession and keeps a current, event-driven screen model."""

    __slots__ = (
        "_active_message",
        "_blocks",
        "_counter",
        "_dispatcher",
        "_retry",
        "_session",
        "_screen_sink",
        "_sink",
        "_tools",
        "_width",
        "lines",
    )

    def __init__(
        self,
        *,
        session: AgentSession,
        dispatcher: CommandDispatcher | None = None,
        sink: Callable[[str], None] | None = None,
        screen_sink: Callable[[tuple[str, ...]], None] | None = None,
        width: int = 80,
    ) -> None:
        self._session = session
        self._dispatcher = dispatcher
        self._width = width
        self._retry = RetryStatusLine()
        self._blocks: OrderedDict[str, tuple[str, ...]] = OrderedDict()
        self._tools: dict[str, ToolExecutionView] = {}
        self._counter = 0
        self._active_message: str | None = None
        self.lines: list[str] = []
        self._sink: Callable[[str], None] = sink or (lambda _line: None)
        self._screen_sink = screen_sink
        session.subscribe(self._on_event)

    async def handle(self, line: str) -> None:
        if self._dispatcher is not None:
            outcome = await self._dispatcher.dispatch(line)
            if outcome is not None:
                if outcome.text:
                    self._append_text(outcome.text)
                return
        await self._session.prompt(line)
        await self._session.wait_for_idle()

    def _next_key(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}:{self._counter}"

    def _append_text(self, text: str) -> None:
        lines = tuple(_pad(chunk, self._width) for chunk in wrap_text(text, self._width))
        self._set_block(self._next_key("text"), lines)

    def _set_block(self, key: str, lines: tuple[str, ...]) -> None:
        self._blocks[key] = lines
        self.lines[:] = [line for block in self._blocks.values() for line in block]
        if self._screen_sink is not None:
            self._screen_sink(tuple(self.lines))
        for line in lines:
            self._sink(line)

    def _on_event(self, event: object, signal: asyncio.Event) -> None:
        del signal
        if isinstance(event, MessageStartEvent) and isinstance(event.message, AssistantMessage):
            self._active_message = self._next_key("assistant")
            self._blocks[self._active_message] = ()
        elif isinstance(event, MessageUpdateEvent):
            self._render_assistant(event.message)
        elif isinstance(event, MessageEndEvent) and isinstance(event.message, AssistantMessage):
            self._render_assistant(event.message)
            self._active_message = None
        elif isinstance(event, ToolExecutionStartEvent):
            view = ToolExecutionView(event.tool_name)
            self._tools[event.tool_call_id] = view
            self._set_block(f"tool:{event.tool_call_id}", view.render(self._width))
        elif isinstance(event, ToolExecutionUpdateEvent):
            view = self._tools.get(event.tool_call_id)
            if view is not None:
                view.update(_result_detail(event.partial_result))
                self._set_block(f"tool:{event.tool_call_id}", view.render(self._width))
        elif isinstance(event, ToolExecutionEndEvent):
            view = self._tools.get(event.tool_call_id)
            if view is not None:
                detail = _result_detail(event.result)
                (view.fail if event.is_error else view.complete)(detail)
                self._set_block(f"tool:{event.tool_call_id}", view.render(self._width))
        elif isinstance(event, AutoRetryStartEvent):
            self._retry.retry_started(
                attempt=event.attempt,
                max_attempts=event.max_attempts,
                delay_seconds=event.delay_seconds,
            )
            self._set_block("retry", self._retry.render(self._width))
        elif isinstance(event, AutoRetryEndEvent):
            self._retry.retry_finished(success=event.success)
            self._set_block("retry", self._retry.render(self._width))

    def _render_assistant(self, message: AssistantMessage) -> None:
        key = self._active_message
        if key is None:
            key = self._next_key("assistant")
            self._active_message = key
        view = AssistantMessageView()
        for block in message.content:
            if isinstance(block, TextContent):
                view.add_text_delta(block.text)
            elif isinstance(block, ThinkingContent):
                view.add_thinking_delta(block.thinking)
        if message.stop_reason in ("error", "aborted"):
            view.fail(message.error_message or "provider error")
        self._set_block(key, view.render(self._width))


def _result_detail(result: object) -> str | None:
    details = getattr(result, "details", None)
    if details in (None, {}, ""):
        return None
    return str(details)


__all__ = ["InteractiveApp"]
