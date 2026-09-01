"""Typed lifecycle events delivered to Python extensions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pi_agent import AgentMessage
from pi_ai import AssistantMessage, AssistantMessageEvent, ToolResultMessage


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
)


__all__ = [
    "AgentSettledEvent",
    "ExtensionAgentEndEvent",
    "ExtensionAgentStartEvent",
    "ExtensionLifecycleEvent",
    "ExtensionMessageEndEvent",
    "ExtensionMessageStartEvent",
    "ExtensionMessageUpdateEvent",
    "ExtensionTurnEndEvent",
    "ExtensionTurnStartEvent",
    "UiPromptEndEvent",
    "UiPromptStartEvent",
]
