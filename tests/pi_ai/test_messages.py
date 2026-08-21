from __future__ import annotations

from typing import cast

import pytest
from pydantic import ValidationError

from pi_ai.messages import (
    AssistantMessage,
    AssistantMessageDiagnostic,
    DeferredHandle,
    DiagnosticErrorInfo,
    ImageContent,
    TextContent,
    ThinkingContent,
    ToolCall,
    ToolResultMessage,
    UserMessage,
)
from pi_ai.usage import Usage, UsageCost
from pi_ai.wire.messages import dump_message, parse_message


def _usage() -> Usage:
    return Usage(
        input=1,
        output=2,
        cache_read=0,
        cache_write=0,
        total_tokens=3,
        cost=UsageCost(input=0.0, output=0.0, cache_read=0.0, cache_write=0.0, total=0.0),
    )


def test_user_message_round_trips_string_and_content_blocks() -> None:
    string_message = UserMessage(content="hello", timestamp=1)
    block_message = UserMessage(
        content=(
            TextContent(text="look", text_signature="text-sig"),
            ImageContent(data="aW1hZ2U=", mime_type="image/png"),
        ),
        timestamp=2,
    )

    assert dump_message(string_message) == {
        "role": "user",
        "content": "hello",
        "timestamp": 1,
    }
    assert dump_message(block_message) == {
        "role": "user",
        "content": [
            {"type": "text", "text": "look", "textSignature": "text-sig"},
            {"type": "image", "data": "aW1hZ2U=", "mimeType": "image/png"},
        ],
        "timestamp": 2,
    }
    assert parse_message(dump_message(string_message)) == string_message
    assert parse_message(dump_message(block_message)) == block_message


def test_assistant_message_round_trips_all_content_discriminators() -> None:
    message = AssistantMessage(
        content=(
            ThinkingContent(
                thinking="reason",
                thinking_signature="thinking-sig",
                redacted=True,
            ),
            TextContent(text="answer"),
            ToolCall(
                id="call-1",
                name="read",
                arguments={"path": "README.md", "offset": 3},
                thought_signature="tool-sig",
                namespace="filesystem",
            ),
        ),
        api="openai-completions",
        provider="deepseek",
        model="deepseek-chat",
        usage=_usage(),
        stop_reason="toolUse",
        timestamp=3,
        response_model="deepseek-v4",
        response_id="response-1",
        diagnostics=(
            AssistantMessageDiagnostic(
                type="provider_warning",
                timestamp=3,
                error=DiagnosticErrorInfo(message="redacted", name="ProviderError", code=429),
                details={"retryable": True},
            ),
        ),
        deferred=DeferredHandle(
            provider="deepseek",
            model_id="deepseek-chat",
            api="openai-completions",
            id="deferred-1",
            expires_at=10,
            poll_after_ms=20,
            data={"partition": 2},
        ),
        error_message="recoverable",
        raw_stop_reason="tool_calls",
        end_turn=False,
    )

    dumped = dump_message(message)

    assert dumped["stopReason"] == "toolUse"
    assert dumped["responseModel"] == "deepseek-v4"
    assert dumped["responseId"] == "response-1"
    assert dumped["endTurn"] is False
    assert dumped["diagnostics"] == [
        {
            "type": "provider_warning",
            "timestamp": 3,
            "error": {"message": "redacted", "name": "ProviderError", "code": 429},
            "details": {"retryable": True},
        }
    ]
    assert dumped["deferred"] == {
        "provider": "deepseek",
        "modelId": "deepseek-chat",
        "api": "openai-completions",
        "id": "deferred-1",
        "expiresAt": 10,
        "pollAfterMs": 20,
        "data": {"partition": 2},
    }
    assert parse_message(dumped) == message


def test_tool_result_round_trips_camel_case_and_json_details() -> None:
    message = ToolResultMessage(
        tool_call_id="call-1",
        tool_name="read",
        content=(TextContent(text="contents"), ImageContent(data="AA==", mime_type="image/png")),
        is_error=False,
        timestamp=4,
        details={"lines": [1, 2]},
        usage=_usage(),
        added_tool_names=("write", "edit"),
    )

    dumped = dump_message(message)

    assert dumped["role"] == "toolResult"
    assert dumped["toolCallId"] == "call-1"
    assert dumped["toolName"] == "read"
    assert dumped["isError"] is False
    assert dumped["addedToolNames"] == ["write", "edit"]
    assert parse_message(dumped) == message


INVALID_PAYLOADS = cast(
    "tuple[object, ...]",
    (
        {"role": "system", "content": "no", "timestamp": 1},
        {"role": "user", "content": [{"type": "audio", "data": "x"}], "timestamp": 1},
        {"role": "user", "content": "hello", "timestamp": "1"},
        {"role": "user", "content": "hello", "timestamp": 1, "secret": "no"},
        {
            "role": "assistant",
            "content": [{"type": "toolCall", "id": "1", "name": "x", "arguments": []}],
            "api": "test",
            "provider": "test",
            "model": "test",
            "usage": {},
            "stopReason": "stop",
            "timestamp": 1,
        },
    ),
)


@pytest.mark.parametrize("payload", INVALID_PAYLOADS)
def test_invalid_message_wire_payloads_are_rejected(payload: object) -> None:
    with pytest.raises(ValidationError):
        parse_message(payload)
