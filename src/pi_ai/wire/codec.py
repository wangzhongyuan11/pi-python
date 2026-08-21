"""Stable JSON encoding and schema entry points for the public AI wire surface."""

from __future__ import annotations

import json

from ..events import AssistantMessageEvent
from ..messages import JsonObject, JsonValue, Message
from ..tools import Tool
from .events import dump_event, event_wire_schema, parse_event
from .messages import dump_message, message_wire_schema, parse_message
from .tools import dump_tool, tool_wire_schema


def _encode(payload: dict[str, JsonValue]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _decode(payload: str | bytes | bytearray) -> object:
    return json.loads(payload)


def encode_message_json(message: Message) -> str:
    return _encode(dump_message(message))


def decode_message_json(payload: str | bytes | bytearray) -> Message:
    return parse_message(_decode(payload))


def encode_event_json(event: AssistantMessageEvent) -> str:
    return _encode(dump_event(event))


def decode_event_json(payload: str | bytes | bytearray) -> AssistantMessageEvent:
    return parse_event(_decode(payload))


def encode_tool_json[ParamsT](tool: Tool[ParamsT]) -> str:
    return _encode(dump_tool(tool))


def message_json_schema() -> JsonObject:
    return message_wire_schema()


def event_json_schema() -> JsonObject:
    return event_wire_schema()


def tool_json_schema() -> JsonObject:
    return tool_wire_schema()


__all__ = [
    "decode_event_json",
    "decode_message_json",
    "encode_event_json",
    "encode_message_json",
    "encode_tool_json",
    "event_json_schema",
    "message_json_schema",
    "tool_json_schema",
]
