"""Interactive product TUI integration: input, events, and rendering."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from pi_ai import AssistantMessage, TextContent, ToolResultMessage
from pi_tui.layout import wrap_text

from ..agent_session import AgentSession
from ..agent_session_events import AutoRetryEndEvent, AutoRetryStartEvent
from .commands import CommandDispatcher
from .render_status import RetryStatusLine
from .render_tools import ToolExecutionView


def _pad(line: str, width: int) -> str:
    return line + " " * max(0, width - len(line))


class InteractiveApp:
    """Drives one AgentSession from input lines into rendered output lines."""

    __slots__ = ("_dispatcher", "_retry", "_session", "_sink", "_width", "lines")

    def __init__(
        self,
        *,
        session: AgentSession,
        dispatcher: CommandDispatcher | None = None,
        sink: Callable[[str], None] | None = None,
        width: int = 80,
    ) -> None:
        self._session = session
        self._dispatcher = dispatcher
        self._width = width
        self._retry = RetryStatusLine()
        self.lines: list[str] = []
        self._sink: Callable[[str], None] = sink or (lambda _line: None)
        session.subscribe(self._on_event)

    async def handle(self, line: str) -> None:
        if self._dispatcher is not None:
            outcome = await self._dispatcher.dispatch(line)
            if outcome is not None:
                if outcome.text:
                    self._emit(outcome.text)
                return
        await self._session.prompt(line)
        await self._session.wait_for_idle()
        self._render_messages()

    def _emit(self, text: str) -> None:
        for chunk in wrap_text(text, self._width):
            rendered = _pad(chunk, self._width)
            self.lines.append(rendered)
            self._sink(rendered)

    def _on_event(self, event: object, signal: asyncio.Event) -> None:
        del signal
        if isinstance(event, AutoRetryStartEvent):
            self._retry.retry_started(
                attempt=event.attempt,
                max_attempts=event.max_attempts,
                delay_seconds=event.delay_seconds,
            )
            self._flush_status()
        elif isinstance(event, AutoRetryEndEvent):
            self._retry.retry_finished(success=event.success)
            self._flush_status()

    def _flush_status(self) -> None:
        for rendered in self._retry.render(self._width):
            self.lines.append(rendered)
            self._sink(rendered)

    def _render_messages(self) -> None:
        for message in self._session.messages:
            if isinstance(message, AssistantMessage):
                text = "".join(
                    block.text for block in message.content if isinstance(block, TextContent)
                )
                if message.stop_reason == "error":
                    self._emit(f"[error] {message.error_message or 'provider error'}")
                    continue
                if text.strip():
                    self._emit(text)
                continue
            if isinstance(message, ToolResultMessage):
                view = ToolExecutionView(str(message.tool_name))
                (view.fail if message.is_error else view.complete)()
                for rendered in view.render(self._width):
                    self.lines.append(rendered)
                    self._sink(rendered)


__all__ = ["InteractiveApp"]
