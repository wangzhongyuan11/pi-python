"""Interactive product TUI integration: input, events, and rendering."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import Callable

from pi_agent import (
    AgentMessage,
    MessageEndEvent,
    MessageStartEvent,
    MessageUpdateEvent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
    ToolExecutionUpdateEvent,
)
from pi_ai import AssistantMessage, TextContent, ThinkingContent, UserMessage
from pi_tui.layout import wrap_text
from pi_tui.width import sanitize_terminal_text, truncate_to_width, visible_width

from ..agent_session import AgentSession
from ..agent_session_events import (
    AutoRetryEndEvent,
    AutoRetryStartEvent,
    CompactionEndEvent,
    CompactionStartEvent,
)
from .commands import CommandDispatcher
from .render_messages import AssistantMessageView
from .render_status import RetryStatusLine, SessionStatusLine
from .render_tools import ToolExecutionView, edit_diff_summary


def _pad(line: str, width: int) -> str:
    return line + " " * max(0, width - visible_width(line))


class InteractiveApp:
    """Drives one AgentSession and keeps a current, event-driven screen model."""

    __slots__ = (
        "_active_message",
        "_block_sink",
        "_blocks",
        "_commit_sink",
        "_compose_prompt",
        "_counter",
        "_dispatcher",
        "_raw_sink",
        "_retry",
        "_screen_sink",
        "_session",
        "_session_status",
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
        block_sink: Callable[[tuple[str, ...]], None] | None = None,
        commit_sink: Callable[[], None] | None = None,
        raw_sink: Callable[[str], None] | None = None,
        compose_prompt: Callable[[str], AgentMessage | str] | None = None,
        initial_lines: tuple[str, ...] = (),
        width: int = 80,
    ) -> None:
        self._session = session
        self._dispatcher = dispatcher
        self._compose_prompt = compose_prompt
        self._width = width
        self._retry = RetryStatusLine()
        self._session_status = SessionStatusLine()
        self._blocks: OrderedDict[str, tuple[str, ...]] = OrderedDict()
        if initial_lines:
            self._blocks["history"] = tuple(initial_lines)
        self._tools: dict[str, ToolExecutionView] = {}
        self._counter = 0
        self._active_message: str | None = None
        self.lines: list[str] = list(initial_lines)
        self._sink: Callable[[str], None] = sink or (lambda _line: None)
        self._screen_sink = screen_sink
        self._block_sink: Callable[[tuple[str, ...]], None] | None = block_sink
        self._commit_sink: Callable[[], None] | None = commit_sink
        self._raw_sink: Callable[[str], None] | None = raw_sink
        if initial_lines:
            # Paint the restored transcript through the active renderer so
            # resumed/switched sessions show their history immediately.
            if self._screen_sink is not None:
                self._screen_sink(tuple(self.lines))
            elif self._block_sink is not None:
                self._block_sink(tuple(initial_lines))
                if self._commit_sink is not None:
                    self._commit_sink()
        session.subscribe(self._on_event)

    def note(self, text: str) -> None:
        """Append a plain transcript block for out-of-band product messages."""

        self._append_text(text)

    async def handle(self, line: str) -> None:
        if self._dispatcher is not None:
            outcome = await self._dispatcher.dispatch(line)
            if outcome is not None:
                if outcome.kind == "raw":
                    self._write_raw(outcome.text)
                elif outcome.text:
                    self._append_text(outcome.text)
                return
        payload: AgentMessage | str = line
        if self._compose_prompt is not None:
            payload = self._compose_prompt(line)
        await self._session.prompt(payload)
        await self._session.wait_for_idle()

    def _write_raw(self, payload: str) -> None:
        """Send a trusted terminal control payload outside the wrapped transcript."""

        if self._raw_sink is not None and payload:
            self._raw_sink(payload)

    def _next_key(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}:{self._counter}"

    def _append_text(self, text: str) -> None:
        lines = tuple(_pad(chunk, self._width) for chunk in wrap_text(text, self._width))
        self._set_block(self._next_key("text"), lines)

    def _set_block(self, key: str, lines: tuple[str, ...], *, live: bool = False) -> None:
        """Update one block; ``live`` blocks keep repainting, settled blocks commit."""

        self._blocks[key] = lines
        self.lines[:] = [line for block in self._blocks.values() for line in block]
        if self._block_sink is not None:
            self._block_sink(lines)
            if not live:
                self._commit()
        elif self._screen_sink is not None:
            self._screen_sink(tuple(self.lines))
        for line in lines:
            self._sink(line)

    def _commit(self) -> None:
        if self._commit_sink is not None:
            self._commit_sink()

    def _on_event(self, event: object, signal: asyncio.Event) -> None:
        del signal
        if isinstance(event, MessageStartEvent) and isinstance(event.message, AssistantMessage):
            self._active_message = self._next_key("assistant")
            self._set_block(self._active_message, (), live=True)
        elif isinstance(event, MessageUpdateEvent):
            self._render_assistant(event.message, live=True)
        elif isinstance(event, MessageEndEvent) and isinstance(event.message, AssistantMessage):
            self._render_assistant(event.message, live=False)
            self._active_message = None
        elif isinstance(event, MessageEndEvent) and isinstance(event.message, UserMessage):
            self._render_user(event.message)
        elif isinstance(event, ToolExecutionStartEvent):
            view = ToolExecutionView(event.tool_name)
            self._tools[event.tool_call_id] = view
            self._set_block(f"tool:{event.tool_call_id}", view.render(self._width), live=True)
        elif isinstance(event, ToolExecutionUpdateEvent):
            view = self._tools.get(event.tool_call_id)
            if view is not None:
                view.update(result_detail(event.partial_result))
                self._set_block(f"tool:{event.tool_call_id}", view.render(self._width), live=True)
        elif isinstance(event, ToolExecutionEndEvent):
            view = self._tools.get(event.tool_call_id)
            if view is not None:
                detail = result_detail(event.result, include_content=event.is_error)
                (view.fail if event.is_error else view.complete)(detail)
                self._set_block(f"tool:{event.tool_call_id}", view.render(self._width))
        elif isinstance(event, AutoRetryStartEvent):
            self._retry.retry_started(
                attempt=event.attempt,
                max_attempts=event.max_attempts,
                delay_seconds=event.delay_seconds,
            )
            self._set_block("retry", self._retry.render(self._width), live=True)
        elif isinstance(event, AutoRetryEndEvent):
            self._retry.retry_finished(success=event.success)
            self._set_block("retry", self._retry.render(self._width))
        elif isinstance(event, CompactionStartEvent):
            self._set_block(
                "session-status",
                self._session_status.compaction_started().render(self._width),
                live=True,
            )
        elif isinstance(event, CompactionEndEvent):
            self._set_block(
                "session-status",
                self._session_status.compaction_finished(tokens_before=event.tokens_before).render(
                    self._width
                ),
            )

    def _render_assistant(self, message: AssistantMessage, *, live: bool) -> None:
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
        if message.stop_reason == "error":
            view.fail(message.error_message or "provider error")
        elif message.stop_reason == "aborted" and message.error_message:
            # A user-initiated cancel keeps the partial answer visible
            # without a misleading provider-error banner.
            view.fail(message.error_message)
        self._set_block(key, view.render(self._width), live=live)

    def _render_user(self, message: UserMessage) -> None:
        content = message.content
        if isinstance(content, str):
            text = content
        else:
            fragments = [block.text for block in content if isinstance(block, TextContent)]
            image_count = len(content) - len(fragments)
            text = "".join(fragments)
            if image_count:
                label = "image" if image_count == 1 else f"{image_count} images"
                text = f"{text} [{label}]".strip()
        self._append_text(f"> {text}")


def result_detail(result: object, *, include_content: bool = False) -> str | None:
    details = getattr(result, "details", None)
    summary = edit_diff_summary(details)
    if summary is not None:
        return summary
    if details not in (None, {}, ""):
        return str(details)
    if not include_content:
        return None
    content = getattr(result, "content", ())
    for block in content:
        if isinstance(block, TextContent):
            summary = " ".join(sanitize_terminal_text(block.text).split())
            if summary:
                return truncate_to_width(summary, 240)
    return None


__all__ = ["InteractiveApp"]
