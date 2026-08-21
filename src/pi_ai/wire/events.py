"""Pydantic wire models and codecs for assistant streaming events."""

from __future__ import annotations

from copy import deepcopy
from typing import Annotated, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from pydantic.alias_generators import to_camel

from ..events import (
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
from ..messages import AssistantMessage, JsonObject, JsonValue, ToolCall
from .messages import AssistantMessageWire, ToolCallWire, dump_message, parse_message


class _EventWire(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_alias=True,
        validate_by_name=True,
        extra="forbid",
        strict=True,
    )


class AssistantMessageStartEventWire(_EventWire):
    type: Literal["start"]
    partial: AssistantMessageWire


class TextStartEventWire(_EventWire):
    type: Literal["text_start"]
    content_index: int = Field(ge=0)
    partial: AssistantMessageWire


class TextDeltaEventWire(_EventWire):
    type: Literal["text_delta"]
    content_index: int = Field(ge=0)
    delta: str
    partial: AssistantMessageWire


class TextEndEventWire(_EventWire):
    type: Literal["text_end"]
    content_index: int = Field(ge=0)
    content: str
    partial: AssistantMessageWire


class ThinkingStartEventWire(_EventWire):
    type: Literal["thinking_start"]
    content_index: int = Field(ge=0)
    partial: AssistantMessageWire


class ThinkingDeltaEventWire(_EventWire):
    type: Literal["thinking_delta"]
    content_index: int = Field(ge=0)
    delta: str
    partial: AssistantMessageWire


class ThinkingEndEventWire(_EventWire):
    type: Literal["thinking_end"]
    content_index: int = Field(ge=0)
    content: str
    partial: AssistantMessageWire


class ToolCallStartEventWire(_EventWire):
    type: Literal["toolcall_start"]
    content_index: int = Field(ge=0)
    partial: AssistantMessageWire


class ToolCallDeltaEventWire(_EventWire):
    type: Literal["toolcall_delta"]
    content_index: int = Field(ge=0)
    delta: str
    partial: AssistantMessageWire


class ToolCallEndEventWire(_EventWire):
    type: Literal["toolcall_end"]
    content_index: int = Field(ge=0)
    tool_call: ToolCallWire
    partial: AssistantMessageWire


class DoneEventWire(_EventWire):
    type: Literal["done"]
    reason: Literal["stop", "length", "toolUse", "deferred"]
    message: AssistantMessageWire


class ErrorEventWire(_EventWire):
    type: Literal["error"]
    reason: Literal["aborted", "error"]
    error: AssistantMessageWire


type AssistantMessageEventWire = Annotated[
    AssistantMessageStartEventWire
    | TextStartEventWire
    | TextDeltaEventWire
    | TextEndEventWire
    | ThinkingStartEventWire
    | ThinkingDeltaEventWire
    | ThinkingEndEventWire
    | ToolCallStartEventWire
    | ToolCallDeltaEventWire
    | ToolCallEndEventWire
    | DoneEventWire
    | ErrorEventWire,
    Field(discriminator="type"),
]

_EVENT_ADAPTER = TypeAdapter[AssistantMessageEventWire](AssistantMessageEventWire)


def _assistant_to_wire(message: AssistantMessage) -> AssistantMessageWire:
    return AssistantMessageWire.model_validate(dump_message(message))


def _assistant_to_domain(message: AssistantMessageWire) -> AssistantMessage:
    parsed = parse_message(message.model_dump(mode="json", by_alias=True, exclude_none=True))
    if not isinstance(parsed, AssistantMessage):
        raise TypeError("assistant event payload did not decode to AssistantMessage")
    return parsed


def _tool_call_to_wire(tool_call: ToolCall) -> ToolCallWire:
    return ToolCallWire(
        type="toolCall",
        id=tool_call.id,
        name=tool_call.name,
        arguments=tool_call.arguments,
        thought_signature=tool_call.thought_signature,
        namespace=tool_call.namespace,
    )


def _tool_call_to_domain(tool_call: ToolCallWire) -> ToolCall:
    return ToolCall(
        id=tool_call.id,
        name=tool_call.name,
        arguments=tool_call.arguments,
        thought_signature=tool_call.thought_signature,
        namespace=tool_call.namespace,
    )


def _event_to_wire(event: AssistantMessageEvent) -> AssistantMessageEventWire:
    if isinstance(event, AssistantMessageStartEvent):
        return AssistantMessageStartEventWire(
            type="start", partial=_assistant_to_wire(event.partial)
        )
    if isinstance(event, TextStartEvent):
        return TextStartEventWire(
            type="text_start",
            content_index=event.content_index,
            partial=_assistant_to_wire(event.partial),
        )
    if isinstance(event, TextDeltaEvent):
        return TextDeltaEventWire(
            type="text_delta",
            content_index=event.content_index,
            delta=event.delta,
            partial=_assistant_to_wire(event.partial),
        )
    if isinstance(event, TextEndEvent):
        return TextEndEventWire(
            type="text_end",
            content_index=event.content_index,
            content=event.content,
            partial=_assistant_to_wire(event.partial),
        )
    if isinstance(event, ThinkingStartEvent):
        return ThinkingStartEventWire(
            type="thinking_start",
            content_index=event.content_index,
            partial=_assistant_to_wire(event.partial),
        )
    if isinstance(event, ThinkingDeltaEvent):
        return ThinkingDeltaEventWire(
            type="thinking_delta",
            content_index=event.content_index,
            delta=event.delta,
            partial=_assistant_to_wire(event.partial),
        )
    if isinstance(event, ThinkingEndEvent):
        return ThinkingEndEventWire(
            type="thinking_end",
            content_index=event.content_index,
            content=event.content,
            partial=_assistant_to_wire(event.partial),
        )
    if isinstance(event, ToolCallStartEvent):
        return ToolCallStartEventWire(
            type="toolcall_start",
            content_index=event.content_index,
            partial=_assistant_to_wire(event.partial),
        )
    if isinstance(event, ToolCallDeltaEvent):
        return ToolCallDeltaEventWire(
            type="toolcall_delta",
            content_index=event.content_index,
            delta=event.delta,
            partial=_assistant_to_wire(event.partial),
        )
    if isinstance(event, ToolCallEndEvent):
        return ToolCallEndEventWire(
            type="toolcall_end",
            content_index=event.content_index,
            tool_call=_tool_call_to_wire(event.tool_call),
            partial=_assistant_to_wire(event.partial),
        )
    if isinstance(event, DoneEvent):
        return DoneEventWire(
            type="done",
            reason=event.reason,
            message=_assistant_to_wire(event.message),
        )
    return ErrorEventWire(
        type="error",
        reason=event.reason,
        error=_assistant_to_wire(event.error),
    )


def _event_to_domain(event: AssistantMessageEventWire) -> AssistantMessageEvent:
    if isinstance(event, AssistantMessageStartEventWire):
        return AssistantMessageStartEvent(partial=_assistant_to_domain(event.partial))
    if isinstance(event, TextStartEventWire):
        return TextStartEvent(
            content_index=event.content_index,
            partial=_assistant_to_domain(event.partial),
        )
    if isinstance(event, TextDeltaEventWire):
        return TextDeltaEvent(
            content_index=event.content_index,
            delta=event.delta,
            partial=_assistant_to_domain(event.partial),
        )
    if isinstance(event, TextEndEventWire):
        return TextEndEvent(
            content_index=event.content_index,
            content=event.content,
            partial=_assistant_to_domain(event.partial),
        )
    if isinstance(event, ThinkingStartEventWire):
        return ThinkingStartEvent(
            content_index=event.content_index,
            partial=_assistant_to_domain(event.partial),
        )
    if isinstance(event, ThinkingDeltaEventWire):
        return ThinkingDeltaEvent(
            content_index=event.content_index,
            delta=event.delta,
            partial=_assistant_to_domain(event.partial),
        )
    if isinstance(event, ThinkingEndEventWire):
        return ThinkingEndEvent(
            content_index=event.content_index,
            content=event.content,
            partial=_assistant_to_domain(event.partial),
        )
    if isinstance(event, ToolCallStartEventWire):
        return ToolCallStartEvent(
            content_index=event.content_index,
            partial=_assistant_to_domain(event.partial),
        )
    if isinstance(event, ToolCallDeltaEventWire):
        return ToolCallDeltaEvent(
            content_index=event.content_index,
            delta=event.delta,
            partial=_assistant_to_domain(event.partial),
        )
    if isinstance(event, ToolCallEndEventWire):
        return ToolCallEndEvent(
            content_index=event.content_index,
            tool_call=_tool_call_to_domain(event.tool_call),
            partial=_assistant_to_domain(event.partial),
        )
    if isinstance(event, DoneEventWire):
        return DoneEvent(reason=event.reason, message=_assistant_to_domain(event.message))
    return ErrorEvent(reason=event.reason, error=_assistant_to_domain(event.error))


def parse_event(payload: object) -> AssistantMessageEvent:
    return _event_to_domain(_EVENT_ADAPTER.validate_python(payload))


def dump_event(event: AssistantMessageEvent) -> dict[str, JsonValue]:
    wire = _event_to_wire(event)
    return cast(
        "dict[str, JsonValue]",
        wire.model_dump(mode="json", by_alias=True, exclude_none=True),
    )


def event_wire_schema() -> JsonObject:
    return deepcopy(
        cast("JsonObject", _EVENT_ADAPTER.json_schema(by_alias=True, mode="validation"))
    )


__all__ = [
    "AssistantMessageEventWire",
    "AssistantMessageStartEventWire",
    "DoneEventWire",
    "ErrorEventWire",
    "TextDeltaEventWire",
    "TextEndEventWire",
    "TextStartEventWire",
    "ThinkingDeltaEventWire",
    "ThinkingEndEventWire",
    "ThinkingStartEventWire",
    "ToolCallDeltaEventWire",
    "ToolCallEndEventWire",
    "ToolCallStartEventWire",
    "dump_event",
    "event_wire_schema",
    "parse_event",
]
