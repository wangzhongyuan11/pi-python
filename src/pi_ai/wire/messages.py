"""Pydantic wire models and codecs for provider-facing messages."""

from __future__ import annotations

from typing import Annotated, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from pydantic.alias_generators import to_camel

from ..messages import (
    AssistantMessage,
    AssistantMessageDiagnostic,
    DeferredHandle,
    DiagnosticErrorInfo,
    ImageContent,
    JsonObject,
    JsonValue,
    Message,
    TextContent,
    ThinkingContent,
    ToolCall,
    ToolResultMessage,
    UserMessage,
)


class _WireModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_alias=True,
        validate_by_name=True,
        extra="forbid",
        strict=True,
    )


class TextContentWire(_WireModel):
    type: Literal["text"]
    text: str
    text_signature: str | None = None


class ThinkingContentWire(_WireModel):
    type: Literal["thinking"]
    thinking: str
    thinking_signature: str | None = None
    redacted: bool | None = None


class ImageContentWire(_WireModel):
    type: Literal["image"]
    data: str
    mime_type: str


class ToolCallWire(_WireModel):
    type: Literal["toolCall"]
    id: str
    name: str
    arguments: JsonObject
    thought_signature: str | None = None
    namespace: str | None = None


type TextOrImageWire = Annotated[TextContentWire | ImageContentWire, Field(discriminator="type")]
type AssistantContentWire = Annotated[
    TextContentWire | ThinkingContentWire | ToolCallWire,
    Field(discriminator="type"),
]


class DiagnosticErrorInfoWire(_WireModel):
    message: str
    name: str | None = None
    code: str | int | None = None


class AssistantMessageDiagnosticWire(_WireModel):
    type: str
    timestamp: int
    error: DiagnosticErrorInfoWire | None = None
    details: JsonObject | None = None


class DeferredHandleWire(_WireModel):
    provider: str
    model_id: str
    api: str
    id: str
    expires_at: int | None = None
    poll_after_ms: int | None = None
    data: JsonValue = None


class UserMessageWire(_WireModel):
    role: Literal["user"]
    content: str | list[TextOrImageWire]
    timestamp: int


class AssistantMessageWire(_WireModel):
    role: Literal["assistant"]
    content: list[AssistantContentWire]
    api: str
    provider: str
    model: str
    usage: JsonObject
    stop_reason: Literal["pending", "stop", "length", "toolUse", "error", "aborted", "deferred"]
    timestamp: int
    response_model: str | None = None
    response_id: str | None = None
    diagnostics: list[AssistantMessageDiagnosticWire] | None = None
    deferred: DeferredHandleWire | None = None
    error_message: str | None = None
    raw_stop_reason: str | None = None
    end_turn: bool | None = None


class ToolResultMessageWire(_WireModel):
    role: Literal["toolResult"]
    tool_call_id: str
    tool_name: str
    content: list[TextOrImageWire]
    details: JsonValue = None
    usage: JsonObject | None = None
    added_tool_names: list[str] | None = None
    is_error: bool
    timestamp: int


type MessageWire = Annotated[
    UserMessageWire | AssistantMessageWire | ToolResultMessageWire,
    Field(discriminator="role"),
]

_MESSAGE_ADAPTER = TypeAdapter[MessageWire](MessageWire)


def _content_to_wire(
    content: TextContent | ThinkingContent | ImageContent | ToolCall,
) -> TextContentWire | ThinkingContentWire | ImageContentWire | ToolCallWire:
    if isinstance(content, TextContent):
        return TextContentWire(
            type="text",
            text=content.text,
            text_signature=content.text_signature,
        )
    if isinstance(content, ThinkingContent):
        return ThinkingContentWire(
            type="thinking",
            thinking=content.thinking,
            thinking_signature=content.thinking_signature,
            redacted=content.redacted,
        )
    if isinstance(content, ImageContent):
        return ImageContentWire(type="image", data=content.data, mime_type=content.mime_type)
    return ToolCallWire(
        type="toolCall",
        id=content.id,
        name=content.name,
        arguments=content.arguments,
        thought_signature=content.thought_signature,
        namespace=content.namespace,
    )


def _content_to_domain(
    content: TextContentWire | ThinkingContentWire | ImageContentWire | ToolCallWire,
) -> TextContent | ThinkingContent | ImageContent | ToolCall:
    if isinstance(content, TextContentWire):
        return TextContent(text=content.text, text_signature=content.text_signature)
    if isinstance(content, ThinkingContentWire):
        return ThinkingContent(
            thinking=content.thinking,
            thinking_signature=content.thinking_signature,
            redacted=content.redacted,
        )
    if isinstance(content, ImageContentWire):
        return ImageContent(data=content.data, mime_type=content.mime_type)
    return ToolCall(
        id=content.id,
        name=content.name,
        arguments=content.arguments,
        thought_signature=content.thought_signature,
        namespace=content.namespace,
    )


def _diagnostic_to_wire(value: AssistantMessageDiagnostic) -> AssistantMessageDiagnosticWire:
    error = value.error
    return AssistantMessageDiagnosticWire(
        type=value.type,
        timestamp=value.timestamp,
        error=(
            None
            if error is None
            else DiagnosticErrorInfoWire(
                message=error.message,
                name=error.name,
                code=error.code,
            )
        ),
        details=value.details,
    )


def _diagnostic_to_domain(value: AssistantMessageDiagnosticWire) -> AssistantMessageDiagnostic:
    error = value.error
    return AssistantMessageDiagnostic(
        type=value.type,
        timestamp=value.timestamp,
        error=(
            None
            if error is None
            else DiagnosticErrorInfo(message=error.message, name=error.name, code=error.code)
        ),
        details=value.details,
    )


def _deferred_to_wire(value: DeferredHandle) -> DeferredHandleWire:
    return DeferredHandleWire(
        provider=value.provider,
        model_id=value.model_id,
        api=value.api,
        id=value.id,
        expires_at=value.expires_at,
        poll_after_ms=value.poll_after_ms,
        data=value.data,
    )


def _deferred_to_domain(value: DeferredHandleWire) -> DeferredHandle:
    return DeferredHandle(
        provider=value.provider,
        model_id=value.model_id,
        api=value.api,
        id=value.id,
        expires_at=value.expires_at,
        poll_after_ms=value.poll_after_ms,
        data=value.data,
    )


def _message_to_wire(message: Message) -> MessageWire:
    if isinstance(message, UserMessage):
        content = (
            message.content
            if isinstance(message.content, str)
            else [cast("TextOrImageWire", _content_to_wire(item)) for item in message.content]
        )
        return UserMessageWire(role="user", content=content, timestamp=message.timestamp)
    if isinstance(message, AssistantMessage):
        diagnostics = (
            None
            if message.diagnostics is None
            else [_diagnostic_to_wire(item) for item in message.diagnostics]
        )
        return AssistantMessageWire(
            role="assistant",
            content=[
                cast("AssistantContentWire", _content_to_wire(item)) for item in message.content
            ],
            api=message.api,
            provider=message.provider,
            model=message.model,
            usage=message.usage,
            stop_reason=message.stop_reason,
            timestamp=message.timestamp,
            response_model=message.response_model,
            response_id=message.response_id,
            diagnostics=diagnostics,
            deferred=None if message.deferred is None else _deferred_to_wire(message.deferred),
            error_message=message.error_message,
            raw_stop_reason=message.raw_stop_reason,
            end_turn=message.end_turn,
        )
    return ToolResultMessageWire(
        role="toolResult",
        tool_call_id=message.tool_call_id,
        tool_name=message.tool_name,
        content=[cast("TextOrImageWire", _content_to_wire(item)) for item in message.content],
        details=message.details,
        usage=message.usage,
        added_tool_names=(
            None if message.added_tool_names is None else list(message.added_tool_names)
        ),
        is_error=message.is_error,
        timestamp=message.timestamp,
    )


def _message_to_domain(message: MessageWire) -> Message:
    if isinstance(message, UserMessageWire):
        content = (
            message.content
            if isinstance(message.content, str)
            else tuple(
                cast("TextContent | ImageContent", _content_to_domain(item))
                for item in message.content
            )
        )
        return UserMessage(content=content, timestamp=message.timestamp)
    if isinstance(message, AssistantMessageWire):
        return AssistantMessage(
            content=tuple(
                cast("TextContent | ThinkingContent | ToolCall", _content_to_domain(item))
                for item in message.content
            ),
            api=message.api,
            provider=message.provider,
            model=message.model,
            usage=message.usage,
            stop_reason=message.stop_reason,
            timestamp=message.timestamp,
            response_model=message.response_model,
            response_id=message.response_id,
            diagnostics=(
                None
                if message.diagnostics is None
                else tuple(_diagnostic_to_domain(item) for item in message.diagnostics)
            ),
            deferred=None if message.deferred is None else _deferred_to_domain(message.deferred),
            error_message=message.error_message,
            raw_stop_reason=message.raw_stop_reason,
            end_turn=message.end_turn,
        )
    return ToolResultMessage(
        tool_call_id=message.tool_call_id,
        tool_name=message.tool_name,
        content=tuple(
            cast("TextContent | ImageContent", _content_to_domain(item)) for item in message.content
        ),
        details=message.details,
        usage=message.usage,
        added_tool_names=(
            None if message.added_tool_names is None else tuple(message.added_tool_names)
        ),
        is_error=message.is_error,
        timestamp=message.timestamp,
    )


def parse_message(payload: object) -> Message:
    """Validate one strict camelCase wire payload and return a domain message."""

    return _message_to_domain(_MESSAGE_ADAPTER.validate_python(payload))


def dump_message(message: Message) -> dict[str, JsonValue]:
    """Encode one domain message using the frozen camelCase wire names."""

    wire = _message_to_wire(message)
    dumped = wire.model_dump(mode="json", by_alias=True, exclude_none=True)
    return cast("dict[str, JsonValue]", dumped)


__all__ = [
    "AssistantMessageDiagnosticWire",
    "AssistantMessageWire",
    "DeferredHandleWire",
    "DiagnosticErrorInfoWire",
    "ImageContentWire",
    "MessageWire",
    "TextContentWire",
    "ThinkingContentWire",
    "ToolCallWire",
    "ToolResultMessageWire",
    "UserMessageWire",
    "dump_message",
    "parse_message",
]
