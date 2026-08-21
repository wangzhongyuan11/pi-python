"""Single-consumer assistant event stream with protocol validation."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Literal

from .events import (
    AssistantMessageEvent,
    AssistantMessageStartEvent,
    DoneEvent,
    ErrorEvent,
    TextDeltaEvent,
    TextEndEvent,
    TextStartEvent,
    ThinkingDeltaEvent,
    ThinkingEndEvent,
    ThinkingStartEvent,
    ToolCallDeltaEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
)
from .messages import AssistantMessage


class StreamProtocolError(RuntimeError):
    """Raised when a producer violates the assistant event protocol."""


class StreamConsumedError(RuntimeError):
    """Raised when a second consumer attempts to iterate the same stream."""


class _EndOfStream:
    __slots__ = ()


_END = _EndOfStream()
type _BlockKind = Literal["text", "thinking", "toolcall"]


class AssistantStream:
    """Queues validated events and exposes their final assistant message."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[AssistantMessageEvent | _EndOfStream] = asyncio.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._result_future: asyncio.Future[AssistantMessage] | None = None
        self._started = False
        self._terminated = False
        self._consumer_claimed = False
        self._open_blocks: dict[int, _BlockKind] = {}
        self._seen_indices: set[int] = set()

    def _bind_to_running_loop(self) -> asyncio.Future[AssistantMessage]:
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
            self._result_future = loop.create_future()
        elif self._loop is not loop:
            raise RuntimeError("AssistantStream cannot be used across event loops")
        if self._result_future is None:
            raise RuntimeError("AssistantStream result future was not initialized")
        return self._result_future

    def _start_block(self, content_index: int, kind: _BlockKind) -> None:
        if content_index in self._seen_indices:
            raise StreamProtocolError(f"content index {content_index} has already started")
        self._seen_indices.add(content_index)
        self._open_blocks[content_index] = kind

    def _require_open_block(self, content_index: int, kind: _BlockKind) -> None:
        if self._open_blocks.get(content_index) != kind:
            raise StreamProtocolError(f"content index {content_index} has no open {kind} block")

    def _validate_event(self, event: AssistantMessageEvent) -> None:
        if self._terminated:
            raise StreamProtocolError("assistant stream has already terminated")
        if not self._started:
            if not isinstance(event, AssistantMessageStartEvent):
                raise StreamProtocolError("first event must be start")
            self._started = True
            return
        if isinstance(event, AssistantMessageStartEvent):
            raise StreamProtocolError("assistant stream may contain only one start event")

        if isinstance(event, TextStartEvent):
            self._start_block(event.content_index, "text")
        elif isinstance(event, TextDeltaEvent):
            self._require_open_block(event.content_index, "text")
        elif isinstance(event, TextEndEvent):
            self._require_open_block(event.content_index, "text")
            del self._open_blocks[event.content_index]
        elif isinstance(event, ThinkingStartEvent):
            self._start_block(event.content_index, "thinking")
        elif isinstance(event, ThinkingDeltaEvent):
            self._require_open_block(event.content_index, "thinking")
        elif isinstance(event, ThinkingEndEvent):
            self._require_open_block(event.content_index, "thinking")
            del self._open_blocks[event.content_index]
        elif isinstance(event, ToolCallStartEvent):
            self._start_block(event.content_index, "toolcall")
        elif isinstance(event, ToolCallDeltaEvent):
            self._require_open_block(event.content_index, "toolcall")
        elif isinstance(event, ToolCallEndEvent):
            self._require_open_block(event.content_index, "toolcall")
            del self._open_blocks[event.content_index]
        elif isinstance(event, DoneEvent):
            self._validate_terminal_reason(event.reason, event.message)
        else:
            self._validate_terminal_reason(event.reason, event.error)

    def _validate_terminal_reason(self, reason: str, message: AssistantMessage) -> None:
        if self._open_blocks:
            raise StreamProtocolError("assistant stream cannot terminate with open content blocks")
        if message.stop_reason != reason:
            raise StreamProtocolError(
                f'terminal reason "{reason}" does not match message stop reason '
                f'"{message.stop_reason}"'
            )

    def push(self, event: AssistantMessageEvent) -> None:
        result_future = self._bind_to_running_loop()
        self._validate_event(event)
        self._queue.put_nowait(event)
        if isinstance(event, DoneEvent):
            self._terminated = True
            result_future.set_result(event.message)
            self._queue.put_nowait(_END)
        elif isinstance(event, ErrorEvent):
            self._terminated = True
            result_future.set_result(event.error)
            self._queue.put_nowait(_END)

    def __aiter__(self) -> AsyncIterator[AssistantMessageEvent]:
        self._bind_to_running_loop()
        if self._consumer_claimed:
            raise StreamConsumedError("AssistantStream supports only one event consumer")
        self._consumer_claimed = True
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[AssistantMessageEvent]:
        while True:
            item = await self._queue.get()
            if isinstance(item, _EndOfStream):
                return
            yield item

    async def result(self) -> AssistantMessage:
        return await asyncio.shield(self._bind_to_running_loop())


def create_assistant_stream() -> AssistantStream:
    return AssistantStream()


__all__ = [
    "AssistantStream",
    "StreamConsumedError",
    "StreamProtocolError",
    "create_assistant_stream",
]
