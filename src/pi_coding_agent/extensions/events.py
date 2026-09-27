"""Typed lifecycle events delivered to Python extensions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pi_agent import AgentMessage
from pi_ai import (
    AssistantMessage,
    AssistantMessageEvent,
    ImageContent,
    TextContent,
    ToolResultMessage,
    Usage,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class UiPromptStartEvent:
    prompt: object
    type: Literal["ui_prompt_start"] = field(default="ui_prompt_start", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class UiPromptEndEvent:
    prompt: object
    type: Literal["ui_prompt_end"] = field(default="ui_prompt_end", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class ExtensionAgentStartEvent:
    type: Literal["agent_start"] = field(default="agent_start", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class ExtensionAgentEndEvent:
    messages: tuple[AgentMessage, ...]
    type: Literal["agent_end"] = field(default="agent_end", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentSettledEvent:
    type: Literal["agent_settled"] = field(default="agent_settled", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class ExtensionTurnStartEvent:
    turn_index: int
    timestamp: int
    type: Literal["turn_start"] = field(default="turn_start", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class ExtensionTurnEndEvent:
    turn_index: int
    message: AssistantMessage
    tool_results: tuple[ToolResultMessage, ...]
    type: Literal["turn_end"] = field(default="turn_end", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class ExtensionMessageStartEvent:
    message: AgentMessage
    type: Literal["message_start"] = field(default="message_start", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class ExtensionMessageUpdateEvent:
    message: AssistantMessage
    assistant_message_event: AssistantMessageEvent
    type: Literal["message_update"] = field(default="message_update", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class ExtensionMessageEndEvent:
    message: AgentMessage
    type: Literal["message_end"] = field(default="message_end", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class ExtensionToolExecutionStartEvent:
    tool_call_id: str
    tool_name: str
    args: object
    type: Literal["tool_execution_start"] = field(default="tool_execution_start", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class ExtensionToolExecutionUpdateEvent:
    tool_call_id: str
    tool_name: str
    args: object
    partial_result: object
    type: Literal["tool_execution_update"] = field(default="tool_execution_update", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class ExtensionToolExecutionEndEvent:
    tool_call_id: str
    tool_name: str
    result: object
    is_error: bool
    type: Literal["tool_execution_end"] = field(default="tool_execution_end", init=False)


@dataclass(slots=True, kw_only=True)
class ContextEvent:
    messages: tuple[AgentMessage, ...]
    type: Literal["context"] = field(default="context", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class ContextEventResult:
    messages: tuple[AgentMessage, ...] | None = None


@dataclass(slots=True, kw_only=True)
class BeforeProviderRequestEvent:
    payload: object
    type: Literal["before_provider_request"] = field(default="before_provider_request", init=False)


@dataclass(slots=True, kw_only=True)
class BeforeProviderHeadersEvent:
    headers: dict[str, str | None]
    type: Literal["before_provider_headers"] = field(default="before_provider_headers", init=False)


@dataclass(slots=True, kw_only=True)
class ToolCallEvent:
    tool_call_id: str
    tool_name: str
    input: dict[str, object]
    type: Literal["tool_call"] = field(default="tool_call", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolCallEventResult:
    block: bool = False
    reason: str | None = None
    terminate: bool = False


@dataclass(slots=True, kw_only=True)
class ToolResultEvent:
    tool_call_id: str
    tool_name: str
    input: dict[str, object]
    content: tuple[TextContent | ImageContent, ...]
    details: object
    is_error: bool
    usage: Usage | None
    type: Literal["tool_result"] = field(default="tool_result", init=False)


type ExtensionLifecycleEvent = (
    UiPromptStartEvent
    | UiPromptEndEvent
    | ExtensionAgentStartEvent
    | ExtensionAgentEndEvent
    | AgentSettledEvent
    | ExtensionTurnStartEvent
    | ExtensionTurnEndEvent
    | ExtensionMessageStartEvent
    | ExtensionMessageUpdateEvent
    | ExtensionMessageEndEvent
    | ExtensionToolExecutionStartEvent
    | ExtensionToolExecutionUpdateEvent
    | ExtensionToolExecutionEndEvent
)

type ExtensionControlEvent = (
    ContextEvent
    | BeforeProviderRequestEvent
    | BeforeProviderHeadersEvent
    | ToolCallEvent
    | ToolResultEvent
)

type ExtensionEvent = ExtensionLifecycleEvent | ExtensionControlEvent


__all__ = [
    "AgentSettledEvent",
    "BeforeProviderHeadersEvent",
    "BeforeProviderRequestEvent",
    "ContextEvent",
    "ContextEventResult",
    "ExtensionAgentEndEvent",
    "ExtensionAgentStartEvent",
    "ExtensionControlEvent",
    "ExtensionEvent",
    "ExtensionLifecycleEvent",
    "ExtensionMessageEndEvent",
    "ExtensionMessageStartEvent",
    "ExtensionMessageUpdateEvent",
    "ExtensionToolExecutionEndEvent",
    "ExtensionToolExecutionStartEvent",
    "ExtensionToolExecutionUpdateEvent",
    "ExtensionTurnEndEvent",
    "ExtensionTurnStartEvent",
    "ToolCallEvent",
    "ToolCallEventResult",
    "ToolResultEvent",
    "UiPromptEndEvent",
    "UiPromptStartEvent",
]
