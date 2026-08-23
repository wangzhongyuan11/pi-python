from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from pi_ai import (
    DoneEvent,
    TextContent,
    ThinkingContent,
)
from pi_ai.events import AssistantMessageEvent
from pi_ai.providers.deepseek.models import DEFAULT_DEEPSEEK_MODEL
from pi_ai.providers.deepseek.stream import adapt_deepseek_stream


async def chunks(*values: object) -> AsyncIterator[object]:
    for value in values:
        await asyncio.sleep(0)
        yield value


async def collect(*values: object) -> list[AssistantMessageEvent]:
    stream = adapt_deepseek_stream(
        DEFAULT_DEEPSEEK_MODEL,
        chunks(*values),
        timestamp_ms=123,
    )
    return [event async for event in stream]


def test_streams_thinking_then_text_with_exact_boundaries() -> None:
    events = asyncio.run(
        collect(
            {
                "id": "response-1",
                "model": "deepseek-v4-pro-0813",
                "choices": [{"delta": {"reasoning_content": "inspect "}, "finish_reason": None}],
            },
            {"choices": [{"delta": {"reasoning_content": "first"}, "finish_reason": None}]},
            {"choices": [{"delta": {"reasoning_content": "", "content": ""}}]},
            {"choices": [{"delta": {"content": "Final "}, "finish_reason": None}]},
            {"choices": [{"delta": {"content": "answer"}, "finish_reason": "stop"}]},
            {
                "choices": [],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "prompt_tokens_details": {"cached_tokens": 25},
                    "completion_tokens_details": {"reasoning_tokens": 10},
                },
            },
        )
    )

    assert [event.type for event in events] == [
        "start",
        "thinking_start",
        "thinking_delta",
        "thinking_delta",
        "text_start",
        "text_delta",
        "text_delta",
        "thinking_end",
        "text_end",
        "done",
    ]
    assert [getattr(event, "delta", None) for event in events] == [
        None,
        None,
        "inspect ",
        "first",
        None,
        "Final ",
        "answer",
        None,
        None,
        None,
    ]

    done = events[-1]
    assert isinstance(done, DoneEvent)
    assert done.reason == "stop"
    assert done.message.content == (
        ThinkingContent(thinking="inspect first", thinking_signature="reasoning_content"),
        TextContent(text="Final answer"),
    )
    assert done.message.timestamp == 123
    assert done.message.response_id == "response-1"
    assert done.message.response_model == "deepseek-v4-pro-0813"
    assert done.message.raw_stop_reason == "stop"
    assert done.message.usage.input == 75
    assert done.message.usage.cache_read == 25
    assert done.message.usage.output == 20
    assert done.message.usage.reasoning == 10
    assert done.message.usage.total_tokens == 120


def test_ignores_empty_and_metadata_only_chunks() -> None:
    events = asyncio.run(
        collect(
            None,
            "not-a-chunk",
            dict[str, object](),
            {"choices": [{"delta": dict[str, object](), "finish_reason": None}]},
            {"choices": [{"delta": {"content": "ok"}, "finish_reason": "length"}]},
        )
    )

    assert [event.type for event in events] == [
        "start",
        "text_start",
        "text_delta",
        "text_end",
        "done",
    ]
    done = events[-1]
    assert isinstance(done, DoneEvent)
    assert done.reason == "length"
