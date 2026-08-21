"""Discriminated events emitted while an assistant message streams."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .messages import AssistantMessage, ToolCall


@dataclass(frozen=True, slots=True, kw_only=True)
class AssistantMessageStartEvent:
    partial: AssistantMessage
    type: Literal["start"] = field(default="start", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class TextStartEvent:
    content_index: int
    partial: AssistantMessage
    type: Literal["text_start"] = field(default="text_start", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class TextDeltaEvent:
    content_index: int
    delta: str
    partial: AssistantMessage
    type: Literal["text_delta"] = field(default="text_delta", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class TextEndEvent:
    content_index: int
    content: str
    partial: AssistantMessage
    type: Literal["text_end"] = field(default="text_end", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class ThinkingStartEvent:
    content_index: int
    partial: AssistantMessage
    type: Literal["thinking_start"] = field(default="thinking_start", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class ThinkingDeltaEvent:
    content_index: int
    delta: str
    partial: AssistantMessage
    type: Literal["thinking_delta"] = field(default="thinking_delta", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class ThinkingEndEvent:
    content_index: int
    content: str
    partial: AssistantMessage
    type: Literal["thinking_end"] = field(default="thinking_end", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolCallStartEvent:
    content_index: int
    partial: AssistantMessage
    type: Literal["toolcall_start"] = field(default="toolcall_start", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolCallDeltaEvent:
    content_index: int
    delta: str
    partial: AssistantMessage
    type: Literal["toolcall_delta"] = field(default="toolcall_delta", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolCallEndEvent:
    content_index: int
    tool_call: ToolCall
    partial: AssistantMessage
    type: Literal["toolcall_end"] = field(default="toolcall_end", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class DoneEvent:
    reason: Literal["stop", "length", "toolUse", "deferred"]
    message: AssistantMessage
    type: Literal["done"] = field(default="done", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class ErrorEvent:
    reason: Literal["aborted", "error"]
    error: AssistantMessage
    type: Literal["error"] = field(default="error", init=False)


type AssistantMessageEvent = (
    AssistantMessageStartEvent
    | TextStartEvent
    | TextDeltaEvent
    | TextEndEvent
    | ThinkingStartEvent
    | ThinkingDeltaEvent
    | ThinkingEndEvent
    | ToolCallStartEvent
    | ToolCallDeltaEvent
    | ToolCallEndEvent
    | DoneEvent
    | ErrorEvent
)


__all__ = [
    "AssistantMessageEvent",
    "AssistantMessageStartEvent",
    "DoneEvent",
    "ErrorEvent",
    "TextDeltaEvent",
    "TextEndEvent",
    "TextStartEvent",
    "ThinkingDeltaEvent",
    "ThinkingEndEvent",
    "ThinkingStartEvent",
    "ToolCallDeltaEvent",
    "ToolCallEndEvent",
    "ToolCallStartEvent",
]
