from __future__ import annotations

import pytest
from pydantic import ValidationError

from pi_ai.events import (
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
from pi_ai.messages import AssistantMessage, StopReason, TextContent, ToolCall
from pi_ai.usage import Usage, UsageCost
from pi_ai.wire.events import dump_event, parse_event


def _message(*, stop_reason: StopReason = "pending") -> AssistantMessage:
    return AssistantMessage(
        content=(TextContent(text="partial"),),
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
        stop_reason=stop_reason,
        timestamp=1,
    )


def test_all_twelve_event_discriminators_round_trip() -> None:
    partial = _message()
    tool_call = ToolCall(id="call-1", name="read", arguments={"path": "README.md"})
    events: tuple[AssistantMessageEvent, ...] = (
        AssistantMessageStartEvent(partial=partial),
        TextStartEvent(content_index=0, partial=partial),
        TextDeltaEvent(content_index=0, delta="a", partial=partial),
        TextEndEvent(content_index=0, content="answer", partial=partial),
        ThinkingStartEvent(content_index=1, partial=partial),
        ThinkingDeltaEvent(content_index=1, delta="r", partial=partial),
        ThinkingEndEvent(content_index=1, content="reason", partial=partial),
        ToolCallStartEvent(content_index=2, partial=partial),
        ToolCallDeltaEvent(content_index=2, delta='{"path":', partial=partial),
        ToolCallEndEvent(content_index=2, tool_call=tool_call, partial=partial),
        DoneEvent(reason="stop", message=_message(stop_reason="stop")),
        ErrorEvent(reason="aborted", error=_message(stop_reason="aborted")),
    )

    dumped = [dump_event(event) for event in events]

    assert [item["type"] for item in dumped] == [
        "start",
        "text_start",
        "text_delta",
        "text_end",
        "thinking_start",
        "thinking_delta",
        "thinking_end",
        "toolcall_start",
        "toolcall_delta",
        "toolcall_end",
        "done",
        "error",
    ]
    assert dumped[2]["contentIndex"] == 0
    assert dumped[9]["toolCall"] == {
        "type": "toolCall",
        "id": "call-1",
        "name": "read",
        "arguments": {"path": "README.md"},
    }
    assert tuple(parse_event(item) for item in dumped) == events


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "unknown"},
        {"type": "done", "reason": "error", "message": {}},
        {"type": "error", "reason": "stop", "error": {}},
        {"type": "text_delta", "contentIndex": "0", "delta": "x", "partial": {}},
        {"type": "start", "partial": {}, "secret": "no"},
    ],
)
def test_invalid_event_payloads_are_rejected(payload: object) -> None:
    with pytest.raises(ValidationError):
        parse_event(payload)
