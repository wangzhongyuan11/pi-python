from __future__ import annotations

import asyncio
from typing import Literal

import pytest

from pi_ai.events import (
    AssistantMessageStartEvent,
    DoneEvent,
    ErrorEvent,
    TextDeltaEvent,
    TextEndEvent,
    TextStartEvent,
)
from pi_ai.messages import AssistantMessage, StopReason, TextContent
from pi_ai.stream import AssistantStream, StreamConsumedError, StreamProtocolError
from pi_ai.usage import Usage, UsageCost


def _message(reason: StopReason = "pending", text: str = "") -> AssistantMessage:
    return AssistantMessage(
        content=() if not text else (TextContent(text=text),),
        api="openai-completions",
        provider="deepseek",
        model="deepseek-chat",
        usage=Usage(
            input=0,
            output=0,
            cache_read=0,
            cache_write=0,
            total_tokens=0,
            cost=UsageCost(input=0, output=0, cache_read=0, cache_write=0, total=0),
        ),
        stop_reason=reason,
        timestamp=1,
    )


def test_stream_delivers_events_and_result_to_independent_waiters() -> None:
    async def scenario() -> None:
        stream = AssistantStream()
        partial = _message()
        final = _message("stop", "answer")
        expected = (
            AssistantMessageStartEvent(partial=partial),
            TextStartEvent(content_index=0, partial=partial),
            TextDeltaEvent(content_index=0, delta="answer", partial=partial),
            TextEndEvent(content_index=0, content="answer", partial=partial),
            DoneEvent(reason="stop", message=final),
        )

        async def collect() -> tuple[object, ...]:
            return tuple([event async for event in stream])

        collector = asyncio.create_task(collect())
        result_waiter = asyncio.create_task(stream.result())
        await asyncio.sleep(0)
        for event in expected:
            stream.push(event)

        assert await collector == expected
        assert await result_waiter is final
        assert await stream.result() is final

    asyncio.run(scenario())


ERROR_REASONS: tuple[Literal["error", "aborted"], ...] = ("error", "aborted")


@pytest.mark.parametrize("reason", ERROR_REASONS)
def test_error_and_abort_are_terminal_results(reason: Literal["error", "aborted"]) -> None:
    async def scenario() -> None:
        stream = AssistantStream()
        partial = _message()
        final = _message(reason)
        stream.push(AssistantMessageStartEvent(partial=partial))
        stream.push(ErrorEvent(reason=reason, error=final))

        assert [event.type async for event in stream] == ["start", "error"]
        assert await stream.result() is final

    asyncio.run(scenario())


def test_duplicate_terminal_and_events_after_terminal_are_rejected() -> None:
    async def scenario() -> None:
        stream = AssistantStream()
        partial = _message()
        final = _message("stop")
        stream.push(AssistantMessageStartEvent(partial=partial))
        stream.push(DoneEvent(reason="stop", message=final))

        with pytest.raises(StreamProtocolError, match="terminated"):
            stream.push(DoneEvent(reason="stop", message=final))
        with pytest.raises(StreamProtocolError, match="terminated"):
            stream.push(TextStartEvent(content_index=0, partial=partial))

    asyncio.run(scenario())


def test_invalid_event_order_and_reason_mismatch_are_rejected() -> None:
    async def scenario() -> None:
        partial = _message()
        stream = AssistantStream()
        with pytest.raises(StreamProtocolError, match="first event"):
            stream.push(TextStartEvent(content_index=0, partial=partial))

        stream.push(AssistantMessageStartEvent(partial=partial))
        with pytest.raises(StreamProtocolError, match="open text block"):
            stream.push(TextDeltaEvent(content_index=0, delta="x", partial=partial))
        stream.push(TextStartEvent(content_index=0, partial=partial))
        with pytest.raises(StreamProtocolError, match="open content blocks"):
            stream.push(DoneEvent(reason="stop", message=_message("stop")))
        stream.push(TextEndEvent(content_index=0, content="", partial=partial))
        with pytest.raises(StreamProtocolError, match="does not match"):
            stream.push(DoneEvent(reason="length", message=_message("stop")))

    asyncio.run(scenario())


def test_stream_is_single_consumer() -> None:
    async def scenario() -> None:
        stream = AssistantStream()
        first = stream.__aiter__()
        with pytest.raises(StreamConsumedError):
            stream.__aiter__()
        del first

    asyncio.run(scenario())
