from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict

from pi_ai.events import DoneEvent
from pi_ai.messages import TextContent, ToolCall
from pi_ai.testing import fake_assistant_message
from pi_ai.tools import Tool
from pi_ai.wire.codec import (
    decode_event_json,
    decode_message_json,
    encode_event_json,
    encode_message_json,
    encode_tool_json,
    event_json_schema,
    message_json_schema,
    tool_json_schema,
)


class EchoParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    text: str


def test_message_and_event_json_codecs_are_stable_and_unicode_safe() -> None:
    message = fake_assistant_message(
        (TextContent(text="你好"), ToolCall(id="调用-1", name="echo", arguments={"text": "世界"})),
        stop_reason="toolUse",
        timestamp=7,
    )
    event = DoneEvent(reason="toolUse", message=message)

    message_json = encode_message_json(message)
    event_json = encode_event_json(event)

    assert message_json == json.dumps(
        json.loads(message_json),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    assert "你好" in message_json
    assert '"stopReason":"toolUse"' in message_json
    assert decode_message_json(message_json) == message
    assert decode_event_json(event_json.encode("utf-8")) == event


def test_tool_json_codec_contains_only_provider_surface() -> None:
    tool = Tool(name="echo", description="Echo text", parameter_type=EchoParameters)

    payload = json.loads(encode_tool_json(tool))

    assert payload["name"] == "echo"
    assert payload["description"] == "Echo text"
    assert payload["parameters"]["type"] == "object"
    assert set(payload) == {"name", "description", "parameters"}


def test_wire_json_schemas_use_frozen_camel_case_names_and_are_detached() -> None:
    message_schema = message_json_schema()
    event_schema = event_json_schema()
    tool_schema = tool_json_schema()

    serialized_message = json.dumps(message_schema, sort_keys=True)
    serialized_event = json.dumps(event_schema, sort_keys=True)
    assert "stopReason" in serialized_message
    assert "toolCallId" in serialized_message
    assert "stop_reason" not in serialized_message
    assert "contentIndex" in serialized_event
    assert "toolCall" in serialized_event
    assert tool_schema["additionalProperties"] is False

    message_schema["mutated"] = True
    assert "mutated" not in message_json_schema()
