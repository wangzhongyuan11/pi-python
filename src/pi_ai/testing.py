"""Deterministic offline provider helpers shared by higher-layer tests."""

from __future__ import annotations

import asyncio
import json
from collections import deque
from collections.abc import Iterable
from dataclasses import replace

from .context import Context
from .events import (
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
from .messages import (
    AssistantContent,
    AssistantMessage,
    StopReason,
    TextContent,
    ThinkingContent,
    ToolCall,
)
from .models import Model, ModelCost
from .provider import StreamOptions
from .stream import AssistantStream
from .usage import Usage, UsageCost


def _zero_usage() -> Usage:
    return Usage(
        input=0,
        output=0,
        cache_read=0,
        cache_write=0,
        total_tokens=0,
        cost=UsageCost(input=0, output=0, cache_read=0, cache_write=0, total=0),
    )


def fake_model() -> Model:
    return Model(
        id="fake-1",
        name="Fake Model",
        api="fake",
        provider="fake",
        base_url="http://localhost:0",
        reasoning=True,
        input=("text", "image"),
        cost=ModelCost(input=0, output=0, cache_read=0, cache_write=0),
        context_window=128_000,
        max_tokens=16_384,
    )


def fake_assistant_message(
    content: str | AssistantContent | TextContent | ThinkingContent | ToolCall,
    *,
    stop_reason: StopReason = "stop",
    error_message: str | None = None,
    timestamp: int = 0,
) -> AssistantMessage:
    if isinstance(content, str):
        normalized: AssistantContent = (TextContent(text=content),)
    elif isinstance(content, TextContent | ThinkingContent | ToolCall):
        normalized = (content,)
    else:
        normalized = content
    return AssistantMessage(
        content=normalized,
        api="fake",
        provider="fake",
        model="fake-1",
        usage=_zero_usage(),
        stop_reason=stop_reason,
        error_message=error_message,
        timestamp=timestamp,
    )


class FakeProvider:
    """A deterministic scripted provider that never performs network I/O."""

    def __init__(
        self,
        responses: Iterable[AssistantMessage] = (),
        *,
        chunk_size: int = 4,
    ) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        self._responses = deque(responses)
        self._chunk_size = chunk_size
        self._models = (fake_model(),)
        self._calls: list[tuple[Model, Context]] = []
        self._tasks: set[asyncio.Task[None]] = set()

    @property
    def id(self) -> str:
        return "fake"

    @property
    def name(self) -> str:
        return "Fake"

    @property
    def models(self) -> tuple[Model, ...]:
        return self._models

    @property
    def call_count(self) -> int:
        return len(self._calls)

    @property
    def calls(self) -> tuple[tuple[Model, Context], ...]:
        return tuple(self._calls)

    @property
    def pending_response_count(self) -> int:
        return len(self._responses)

    def set_responses(self, responses: Iterable[AssistantMessage]) -> None:
        self._responses = deque(responses)

    def append_responses(self, responses: Iterable[AssistantMessage]) -> None:
        self._responses.extend(responses)

    def stream(
        self,
        model: Model,
        context: Context,
        options: StreamOptions | None = None,
    ) -> AssistantStream:
        stream = AssistantStream()
        self._calls.append((model, context))
        response = self._responses.popleft() if self._responses else None
        task = asyncio.create_task(self._produce(stream, model, response, options))
        self._tasks.add(task)
        task.add_done_callback(self._task_finished)
        return stream

    def _task_finished(self, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)
        if not task.cancelled():
            task.exception()

    async def _produce(
        self,
        stream: AssistantStream,
        model: Model,
        response: AssistantMessage | None,
        options: StreamOptions | None,
    ) -> None:
        message = self._normalize_response(model, response)
        partial = replace(
            message,
            content=(),
            stop_reason="pending",
            error_message=None,
            deferred=None,
        )
        stream.push(AssistantMessageStartEvent(partial=partial))
        if self._is_aborted(options):
            self._push_aborted(stream, partial)
            return

        for index, block in enumerate(message.content):
            partial = await self._stream_block(stream, partial, block, index, options)
            if self._is_aborted(options):
                self._push_aborted(stream, partial)
                return

        if message.stop_reason == "pending":
            message = replace(
                message,
                stop_reason="error",
                error_message="Fake response ended without a stop reason",
            )
        if message.stop_reason in ("error", "aborted"):
            stream.push(ErrorEvent(reason=message.stop_reason, error=message))
        elif message.stop_reason in ("stop", "length", "toolUse", "deferred"):
            stream.push(DoneEvent(reason=message.stop_reason, message=message))
        else:
            raise TypeError("fake response stop reason was not normalized")

    def _normalize_response(
        self,
        model: Model,
        response: AssistantMessage | None,
    ) -> AssistantMessage:
        if response is None:
            return AssistantMessage(
                content=(),
                api=model.api,
                provider=model.provider,
                model=model.id,
                usage=_zero_usage(),
                stop_reason="error",
                error_message="No more fake responses queued",
                timestamp=self.call_count,
            )
        return replace(response, api=model.api, provider=model.provider, model=model.id)

    async def _stream_block(
        self,
        stream: AssistantStream,
        partial: AssistantMessage,
        block: TextContent | ThinkingContent | ToolCall,
        index: int,
        options: StreamOptions | None,
    ) -> AssistantMessage:
        if isinstance(block, TextContent):
            partial = replace(partial, content=(*partial.content, TextContent(text="")))
            stream.push(TextStartEvent(content_index=index, partial=partial))
            for chunk in self._chunks(block.text):
                partial_block = TextContent(text=_require_text(partial.content[index]).text + chunk)
                partial = replace(partial, content=(*partial.content[:index], partial_block))
                stream.push(TextDeltaEvent(content_index=index, delta=chunk, partial=partial))
                await asyncio.sleep(0)
                if self._is_aborted(options):
                    return partial
            stream.push(TextEndEvent(content_index=index, content=block.text, partial=partial))
            return partial

        if isinstance(block, ThinkingContent):
            partial = replace(partial, content=(*partial.content, ThinkingContent(thinking="")))
            stream.push(ThinkingStartEvent(content_index=index, partial=partial))
            for chunk in self._chunks(block.thinking):
                current = partial.content[index]
                if not isinstance(current, ThinkingContent):
                    raise TypeError("fake thinking block state is invalid")
                partial_block = replace(current, thinking=current.thinking + chunk)
                partial = replace(partial, content=(*partial.content[:index], partial_block))
                stream.push(ThinkingDeltaEvent(content_index=index, delta=chunk, partial=partial))
                await asyncio.sleep(0)
                if self._is_aborted(options):
                    return partial
            stream.push(
                ThinkingEndEvent(content_index=index, content=block.thinking, partial=partial)
            )
            return partial

        partial_call = replace(block, arguments={})
        partial = replace(partial, content=(*partial.content, partial_call))
        stream.push(ToolCallStartEvent(content_index=index, partial=partial))
        serialized = json.dumps(
            block.arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        for chunk in self._chunks(serialized):
            stream.push(ToolCallDeltaEvent(content_index=index, delta=chunk, partial=partial))
            await asyncio.sleep(0)
            if self._is_aborted(options):
                return partial
        partial = replace(partial, content=(*partial.content[:index], block))
        stream.push(
            ToolCallEndEvent(
                content_index=index,
                tool_call=block,
                partial=partial,
            )
        )
        return partial

    def _chunks(self, value: str) -> tuple[str, ...]:
        if not value:
            return ("",)
        return tuple(
            value[index : index + self._chunk_size]
            for index in range(0, len(value), self._chunk_size)
        )

    @staticmethod
    def _is_aborted(options: StreamOptions | None) -> bool:
        return (
            options is not None and options.abort_event is not None and options.abort_event.is_set()
        )

    @staticmethod
    def _push_aborted(stream: AssistantStream, partial: AssistantMessage) -> None:
        aborted = replace(
            partial,
            stop_reason="aborted",
            error_message="Request was aborted",
        )
        stream.push(ErrorEvent(reason="aborted", error=aborted))


def _require_text(content: TextContent | ThinkingContent | ToolCall) -> TextContent:
    if not isinstance(content, TextContent):
        raise TypeError("fake text block state is invalid")
    return content


__all__ = ["FakeProvider", "fake_assistant_message", "fake_model"]
