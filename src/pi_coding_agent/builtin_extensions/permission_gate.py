"""Opt-in per-tool permission gate; disabled by default like upstream."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pi_agent import AgentTool, AgentToolResult, AgentToolUpdateCallback


@dataclass(frozen=True, slots=True)
class PermissionDecision:
    tool: str
    allowed: bool


class PermissionDeniedError(PermissionError):
    """A tool call was rejected by the enabled permission gate."""


class PermissionGate:
    """When disabled every tool runs; when enabled the confirmer decides."""

    __slots__ = ("_confirmer", "_enabled")

    def __init__(
        self,
        *,
        enabled: bool = False,
        confirmer: Callable[[str], bool] | None = None,
    ) -> None:
        self._enabled = enabled
        self._confirmer = confirmer

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False

    def decide(self, tool_name: str) -> PermissionDecision:
        if not self._enabled:
            return PermissionDecision(tool=tool_name, allowed=True)
        if self._confirmer is None:
            return PermissionDecision(tool=tool_name, allowed=False)
        return PermissionDecision(tool=tool_name, allowed=bool(self._confirmer(tool_name)))

    def wrap_tool(self, tool: AgentTool[Any, Any]) -> AgentTool[Any, Any]:
        if not self._enabled:
            return tool

        async def execute(
            tool_call_id: str,
            params: Any,
            abort_event: asyncio.Event | None,
            on_update: AgentToolUpdateCallback[Any] | None,
        ) -> AgentToolResult[Any]:
            decision = self.decide(tool.name)
            if not decision.allowed:
                raise PermissionDeniedError(f"tool {tool.name!r} was denied")
            return await tool.execute(tool_call_id, params, abort_event, on_update)

        return AgentTool(
            name=tool.name,
            label=tool.label,
            description=tool.description,
            parameter_type=tool.parameter_type,
            execute=execute,
            prepare_arguments=tool.prepare_arguments,
            execution_mode=tool.execution_mode,
        )

    def wrap_tools(self, tools: tuple[AgentTool[Any, Any], ...]) -> tuple[AgentTool[Any, Any], ...]:
        return tuple(self.wrap_tool(tool) for tool in tools)


__all__ = ["PermissionDecision", "PermissionDeniedError", "PermissionGate"]
