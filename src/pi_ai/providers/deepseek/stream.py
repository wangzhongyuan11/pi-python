"""Adapt DeepSeek OpenAI-compatible chunks to the Pi assistant event protocol."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import replace
from typing import Any, cast

from ...events import (
    AssistantMessageStartEvent,
    DoneEvent,
    ErrorEvent,
    TextDeltaEvent,
    TextEndEvent,
    TextStartEvent,
    ThinkingDeltaEvent,
    ThinkingEndEvent,
    ThinkingStartEvent,
)
from ...messages import AssistantMessage, StopReason, TextContent, ThinkingContent
from ...models import Model
from ...stream import AssistantStream
from ...usage import Usage, UsageCost


def _field(value: object, name: str) -> object | None:
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        return mapping.get(name)
    return cast("object | None", getattr(value, name, None))


def _integer(value: object | None) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _zero_usage() -> Usage:
    return Usage(
        input=0,
        output=0,
        cache_read=0,
        cache_write=0,
        total_tokens=0,
        cost=UsageCost(input=0, output=0, cache_read=0, cache_write=0, total=0),
        reasoning=0,
    )


def _replace_message(message: AssistantMessage, **changes: Any) -> AssistantMessage:
    return replace(message, **changes)


def _parse_usage(raw: object, model: Model) -> Usage:
    prompt_tokens = _integer(_field(raw, "prompt_tokens"))
    output = _integer(_field(raw, "completion_tokens"))
    prompt_details = _field(raw, "prompt_tokens_details")
    completion_details = _field(raw, "completion_tokens_details")
    cache_read = _integer(_field(prompt_details, "cached_tokens"))
    if cache_read == 0:
        cache_read = _integer(_field(raw, "prompt_cache_hit_tokens"))
    cache_write = _integer(_field(prompt_details, "cache_write_tokens"))
    reasoning = _integer(_field(completion_details, "reasoning_tokens"))
    input_tokens = max(0, prompt_tokens - cache_read - cache_write)
    input_cost = input_tokens * model.cost.input / 1_000_000
    output_cost = output * model.cost.output / 1_000_000
    cache_read_cost = cache_read * model.cost.cache_read / 1_000_000
    cache_write_cost = cache_write * model.cost.cache_write / 1_000_000
    return Usage(
        input=input_tokens,
        output=output,
        cache_read=cache_read,
        cache_write=cache_write,
        total_tokens=input_tokens + output + cache_read + cache_write,
        reasoning=reasoning,
        cost=UsageCost(
            input=input_cost,
            output=output_cost,
            cache_read=cache_read_cost,
            cache_write=cache_write_cost,
            total=input_cost + output_cost + cache_read_cost + cache_write_cost,
        ),
    )


def _finish_reason(value: object) -> tuple[StopReason, str | None]:
    if value in ("stop", "end"):
        return "stop", None
    if value == "length":
        return "length", None
    if value in ("tool_calls", "function_call"):
        return "toolUse", None
    return "error", f"DeepSeek returned unsupported finish reason: {value}"


def _first_choice(chunk: object) -> object | None:
    choices = _field(chunk, "choices")
    if not isinstance(choices, list | tuple) or not choices:
        return None
    return cast("Sequence[object]", choices)[0]


async def _produce(
    stream: AssistantStream,
    model: Model,
    chunks: AsyncIterator[object],
    timestamp_ms: int,
) -> None:
    partial = AssistantMessage(
        content=(),
        api=model.api,
        provider=model.provider,
        model=model.id,
        usage=_zero_usage(),
        stop_reason="pending",
        timestamp=timestamp_ms,
    )
    stream.push(AssistantMessageStartEvent(partial=partial))
    thinking_index: int | None = None
    text_index: int | None = None
    raw_finish_reason: str | None = None
    stop_reason: StopReason = "pending"
    error_message: str | None = None

    try:
        async for chunk in chunks:
            if chunk is None or isinstance(chunk, str | bytes | int | float | bool):
                continue
            response_id = _field(chunk, "id")
            response_model = _field(chunk, "model")
            if isinstance(response_id, str) and response_id and partial.response_id is None:
                partial = _replace_message(partial, response_id=response_id)
            if (
                isinstance(response_model, str)
                and response_model
                and response_model != model.id
                and partial.response_model is None
            ):
                partial = _replace_message(partial, response_model=response_model)

            raw_usage = _field(chunk, "usage")
            if raw_usage is not None:
                partial = _replace_message(partial, usage=_parse_usage(raw_usage, model))

            choice = _first_choice(chunk)
            if choice is None:
                continue
            finish = _field(choice, "finish_reason")
            if isinstance(finish, str) and finish:
                raw_finish_reason = finish
                stop_reason, error_message = _finish_reason(finish)

            delta = _field(choice, "delta")
            if delta is None:
                continue
            reasoning = _field(delta, "reasoning_content")
            if isinstance(reasoning, str) and reasoning:
                if thinking_index is None:
                    thinking_index = len(partial.content)
                    partial = _replace_message(
                        partial,
                        content=(
                            *partial.content,
                            ThinkingContent(
                                thinking="",
                                thinking_signature="reasoning_content",
                            ),
                        ),
                    )
                    stream.push(
                        ThinkingStartEvent(content_index=thinking_index, partial=partial)
                    )
                current = partial.content[thinking_index]
                if not isinstance(current, ThinkingContent):
                    raise TypeError("DeepSeek thinking stream state is invalid")
                updated = replace(current, thinking=current.thinking + reasoning)
                partial = _replace_message(
                    partial,
                    content=(
                        *partial.content[:thinking_index],
                        updated,
                        *partial.content[thinking_index + 1 :],
                    ),
                )
                stream.push(
                    ThinkingDeltaEvent(
                        content_index=thinking_index,
                        delta=reasoning,
                        partial=partial,
                    )
                )

            content = _field(delta, "content")
            if isinstance(content, str) and content:
                if text_index is None:
                    text_index = len(partial.content)
                    partial = _replace_message(
                        partial,
                        content=(*partial.content, TextContent(text="")),
                    )
                    stream.push(TextStartEvent(content_index=text_index, partial=partial))
                current = partial.content[text_index]
                if not isinstance(current, TextContent):
                    raise TypeError("DeepSeek text stream state is invalid")
                updated = replace(current, text=current.text + content)
                partial = _replace_message(
                    partial,
                    content=(
                        *partial.content[:text_index],
                        updated,
                        *partial.content[text_index + 1 :],
                    ),
                )
                stream.push(
                    TextDeltaEvent(content_index=text_index, delta=content, partial=partial)
                )

        if stop_reason == "pending":
            raise RuntimeError("DeepSeek stream ended without finish_reason")
        if stop_reason == "error":
            raise RuntimeError(error_message or "DeepSeek stream failed")

        for index, block in enumerate(partial.content):
            if isinstance(block, ThinkingContent):
                stream.push(
                    ThinkingEndEvent(content_index=index, content=block.thinking, partial=partial)
                )
            elif isinstance(block, TextContent):
                stream.push(TextEndEvent(content_index=index, content=block.text, partial=partial))

        completed = _replace_message(
            partial,
            stop_reason=stop_reason,
            raw_stop_reason=raw_finish_reason,
        )
        if stop_reason not in ("stop", "length", "toolUse", "deferred"):
            raise RuntimeError("DeepSeek stream produced an invalid terminal reason")
        stream.push(DoneEvent(reason=stop_reason, message=completed))
    except Exception as error:
        failed = _replace_message(partial, stop_reason="error", error_message=str(error))
        stream.push(ErrorEvent(reason="error", error=failed))


def adapt_deepseek_stream(
    model: Model,
    chunks: AsyncIterator[object],
    *,
    timestamp_ms: int | None = None,
) -> AssistantStream:
    stream = AssistantStream()
    timestamp = int(time.time() * 1000) if timestamp_ms is None else timestamp_ms
    task = asyncio.create_task(_produce(stream, model, chunks, timestamp))
    task.add_done_callback(_consume_task_exception)
    return stream


def _consume_task_exception(task: asyncio.Task[None]) -> None:
    if not task.cancelled():
        task.exception()


__all__ = ["adapt_deepseek_stream"]
