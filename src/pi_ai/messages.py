"""Provider-facing message and content domain objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .usage import Usage

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]
type StopReason = Literal["pending", "stop", "length", "toolUse", "error", "aborted", "deferred"]


@dataclass(frozen=True, slots=True, kw_only=True)
class TextContent:
    text: str
    text_signature: str | None = None
    type: Literal["text"] = field(default="text", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class ThinkingContent:
    thinking: str
    thinking_signature: str | None = None
    redacted: bool | None = None
    type: Literal["thinking"] = field(default="thinking", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class ImageContent:
    data: str
    mime_type: str
    type: Literal["image"] = field(default="image", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolCall:
    id: str
    name: str
    arguments: JsonObject
    thought_signature: str | None = None
    namespace: str | None = None
    type: Literal["toolCall"] = field(default="toolCall", init=False)


type UserContent = str | tuple[TextContent | ImageContent, ...]
type AssistantContent = tuple[TextContent | ThinkingContent | ToolCall, ...]
type ToolResultContent = tuple[TextContent | ImageContent, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class DiagnosticErrorInfo:
    message: str
    name: str | None = None
    code: str | int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class AssistantMessageDiagnostic:
    type: str
    timestamp: int
    error: DiagnosticErrorInfo | None = None
    details: JsonObject | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class DeferredHandle:
    provider: str
    model_id: str
    api: str
    id: str
    expires_at: int | None = None
    poll_after_ms: int | None = None
    data: JsonValue = None


@dataclass(frozen=True, slots=True, kw_only=True)
class UserMessage:
    content: UserContent
    timestamp: int
    role: Literal["user"] = field(default="user", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class AssistantMessage:
    content: AssistantContent
    api: str
    provider: str
    model: str
    usage: Usage
    stop_reason: StopReason
    timestamp: int
    response_model: str | None = None
    response_id: str | None = None
    diagnostics: tuple[AssistantMessageDiagnostic, ...] | None = None
    deferred: DeferredHandle | None = None
    error_message: str | None = None
    raw_stop_reason: str | None = None
    end_turn: bool | None = None
    role: Literal["assistant"] = field(default="assistant", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolResultMessage:
    tool_call_id: str
    tool_name: str
    content: ToolResultContent
    is_error: bool
    timestamp: int
    details: JsonValue = None
    usage: Usage | None = None
    added_tool_names: tuple[str, ...] | None = None
    role: Literal["toolResult"] = field(default="toolResult", init=False)


type Message = UserMessage | AssistantMessage | ToolResultMessage


__all__ = [
    "AssistantContent",
    "AssistantMessage",
    "AssistantMessageDiagnostic",
    "DeferredHandle",
    "DiagnosticErrorInfo",
    "ImageContent",
    "JsonObject",
    "JsonValue",
    "Message",
    "StopReason",
    "TextContent",
    "ThinkingContent",
    "ToolCall",
    "ToolResultContent",
    "ToolResultMessage",
    "UserContent",
    "UserMessage",
]
