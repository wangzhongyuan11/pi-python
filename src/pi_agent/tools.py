"""Executable agent tools built on provider-visible tool schemas."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from pi_ai import ImageContent, TextContent, Tool, Usage

type ToolExecutionMode = Literal["sequential", "parallel"]


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentToolResult[DetailsT]:
    content: tuple[TextContent | ImageContent, ...]
    details: DetailsT
    usage: Usage | None = None
    added_tool_names: tuple[str, ...] | None = None
    terminate: bool = False


type AgentToolUpdateCallback[DetailsT] = Callable[[AgentToolResult[DetailsT]], None]
type AgentToolExecute[ParamsT, DetailsT] = Callable[
    [str, ParamsT, asyncio.Event | None, AgentToolUpdateCallback[DetailsT] | None],
    Awaitable[AgentToolResult[DetailsT]],
]
type PrepareArguments = Callable[[object], object]


class AgentTool[ParamsT, DetailsT](Tool[ParamsT]):
    __slots__ = ("_execute", "_prepare_arguments", "execution_mode", "label")

    def __init__(
        self,
        *,
        name: str,
        label: str,
        description: str,
        parameter_type: type[ParamsT],
        execute: AgentToolExecute[ParamsT, DetailsT],
        prepare_arguments: PrepareArguments | None = None,
        execution_mode: ToolExecutionMode | None = None,
    ) -> None:
        super().__init__(name=name, description=description, parameter_type=parameter_type)
        if not label:
            raise ValueError("tool label must not be empty")
        self.label = label
        self._execute = execute
        self._prepare_arguments = prepare_arguments
        self.execution_mode = execution_mode

    def prepare_arguments(self, raw: object) -> object:
        if self._prepare_arguments is None:
            return raw
        return self._prepare_arguments(raw)

    async def execute(
        self,
        tool_call_id: str,
        params: ParamsT,
        abort_event: asyncio.Event | None = None,
        on_update: AgentToolUpdateCallback[DetailsT] | None = None,
    ) -> AgentToolResult[DetailsT]:
        return await self._execute(tool_call_id, params, abort_event, on_update)


__all__ = [
    "AgentTool",
    "AgentToolExecute",
    "AgentToolResult",
    "AgentToolUpdateCallback",
    "PrepareArguments",
    "ToolExecutionMode",
]
