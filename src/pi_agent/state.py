"""Immutable public snapshots of agent runtime state."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from pi_ai import AssistantMessage, Model, ModelThinkingLevel

from .messages import AgentMessage
from .tools import AgentTool


@dataclass(frozen=True, slots=True, init=False)
class AgentState:
    system_prompt: str
    model: Model
    thinking_level: ModelThinkingLevel
    tools: tuple[AgentTool[Any, Any], ...]
    messages: tuple[AgentMessage, ...]
    is_streaming: bool
    streaming_message: AssistantMessage | None
    pending_tool_calls: frozenset[str]
    error_message: str | None

    def __init__(
        self,
        *,
        system_prompt: str,
        model: Model,
        thinking_level: ModelThinkingLevel = "off",
        tools: Iterable[AgentTool[Any, Any]] = (),
        messages: Iterable[AgentMessage] = (),
        is_streaming: bool = False,
        streaming_message: AssistantMessage | None = None,
        pending_tool_calls: Iterable[str] = (),
        error_message: str | None = None,
    ) -> None:
        pending = frozenset(pending_tool_calls)
        if not is_streaming and streaming_message is not None:
            raise ValueError("idle agent cannot have a streaming message")
        if not is_streaming and pending:
            raise ValueError("idle agent cannot have pending tool calls")
        object.__setattr__(self, "system_prompt", system_prompt)
        object.__setattr__(self, "model", model)
        object.__setattr__(self, "thinking_level", thinking_level)
        object.__setattr__(self, "tools", tuple(tools))
        object.__setattr__(self, "messages", tuple(messages))
        object.__setattr__(self, "is_streaming", is_streaming)
        object.__setattr__(self, "streaming_message", streaming_message)
        object.__setattr__(self, "pending_tool_calls", pending)
        object.__setattr__(self, "error_message", error_message)


__all__ = ["AgentState"]
