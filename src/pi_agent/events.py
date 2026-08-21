"""Agent lifecycle events and their ordering validator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pi_ai import AssistantMessage, AssistantMessageEvent, JsonObject, ToolResultMessage

from .messages import AgentMessage


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentStartEvent:
    type: Literal["agent_start"] = field(default="agent_start", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentEndEvent:
    messages: tuple[AgentMessage, ...]
    type: Literal["agent_end"] = field(default="agent_end", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class TurnStartEvent:
    type: Literal["turn_start"] = field(default="turn_start", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class TurnEndEvent:
    message: AssistantMessage
    tool_results: tuple[ToolResultMessage, ...]
    type: Literal["turn_end"] = field(default="turn_end", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class MessageStartEvent:
    message: AgentMessage
    type: Literal["message_start"] = field(default="message_start", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class MessageUpdateEvent:
    message: AssistantMessage
    assistant_message_event: AssistantMessageEvent
    type: Literal["message_update"] = field(default="message_update", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class MessageEndEvent:
    message: AgentMessage
    type: Literal["message_end"] = field(default="message_end", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolExecutionStartEvent:
    tool_call_id: str
    tool_name: str
    args: JsonObject
    type: Literal["tool_execution_start"] = field(default="tool_execution_start", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolExecutionUpdateEvent:
    tool_call_id: str
    tool_name: str
    args: JsonObject
    partial_result: object
    type: Literal["tool_execution_update"] = field(default="tool_execution_update", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolExecutionEndEvent:
    tool_call_id: str
    tool_name: str
    result: object
    is_error: bool
    type: Literal["tool_execution_end"] = field(default="tool_execution_end", init=False)


type AgentEvent = (
    AgentStartEvent
    | AgentEndEvent
    | TurnStartEvent
    | TurnEndEvent
    | MessageStartEvent
    | MessageUpdateEvent
    | MessageEndEvent
    | ToolExecutionStartEvent
    | ToolExecutionUpdateEvent
    | ToolExecutionEndEvent
)


class AgentEventSequence:
    """Validate lifecycle nesting without owning transcript state."""

    __slots__ = ("_active_message_role", "_agent_active", "_pending_tools", "_turn_active")

    def __init__(self) -> None:
        self._agent_active = False
        self._turn_active = False
        self._active_message_role: str | None = None
        self._pending_tools: set[str] = set()

    @property
    def is_idle(self) -> bool:
        return not self._agent_active

    def accept(self, event: AgentEvent) -> None:
        if isinstance(event, AgentStartEvent):
            if self._agent_active:
                raise RuntimeError("agent_start requires an idle agent")
            self._agent_active = True
        elif isinstance(event, AgentEndEvent):
            if not self._agent_active:
                raise RuntimeError("agent_end requires an active agent")
            if self._turn_active:
                raise RuntimeError("agent_end requires the turn to finish")
            if self._active_message_role is not None or self._pending_tools:
                raise RuntimeError("agent_end requires all nested work to finish")
            self._agent_active = False
        elif isinstance(event, TurnStartEvent):
            if not self._agent_active:
                raise RuntimeError("turn_start requires an active agent")
            if self._turn_active:
                raise RuntimeError("turn_start requires the previous turn to finish")
            self._turn_active = True
        elif isinstance(event, TurnEndEvent):
            if not self._turn_active:
                raise RuntimeError("turn_end requires an active turn")
            if self._active_message_role is not None or self._pending_tools:
                raise RuntimeError("turn_end requires all messages and tools to finish")
            self._turn_active = False
        elif isinstance(event, MessageStartEvent):
            if not self._turn_active:
                raise RuntimeError("message_start requires an active turn")
            if self._active_message_role is not None:
                raise RuntimeError("message_start requires the previous message to finish")
            self._active_message_role = event.message.role
        elif isinstance(event, MessageUpdateEvent):
            if self._active_message_role != "assistant":
                raise RuntimeError("message_update requires an active assistant message")
        elif isinstance(event, MessageEndEvent):
            if self._active_message_role is None:
                raise RuntimeError("message_end requires an active message")
            if event.message.role != self._active_message_role:
                raise RuntimeError("message_end role must match message_start")
            self._active_message_role = None
        elif isinstance(event, ToolExecutionStartEvent):
            if not self._turn_active or self._active_message_role is not None:
                raise RuntimeError("tool_execution_start requires an active turn between messages")
            if event.tool_call_id in self._pending_tools:
                raise RuntimeError("tool call is already executing")
            self._pending_tools.add(event.tool_call_id)
        elif isinstance(event, ToolExecutionUpdateEvent):
            if event.tool_call_id not in self._pending_tools:
                raise RuntimeError("tool_execution_update requires a pending tool call")
        else:
            if event.tool_call_id not in self._pending_tools:
                raise RuntimeError("tool_execution_end requires a pending tool call")
            self._pending_tools.remove(event.tool_call_id)


__all__ = [
    "AgentEndEvent",
    "AgentEvent",
    "AgentEventSequence",
    "AgentStartEvent",
    "MessageEndEvent",
    "MessageStartEvent",
    "MessageUpdateEvent",
    "ToolExecutionEndEvent",
    "ToolExecutionStartEvent",
    "ToolExecutionUpdateEvent",
    "TurnEndEvent",
    "TurnStartEvent",
]
