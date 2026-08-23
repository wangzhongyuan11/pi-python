"""Schedule a model tool-call batch without changing source-order results."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from pi_ai import AssistantMessage, ToolCall

from .context import AgentContext
from .events import AgentEvent, MessageEndEvent, MessageStartEvent
from .tool_pipeline import (
    AfterToolCallHook,
    BeforeToolCallHook,
    ToolCallOutcome,
    execute_tool_call,
)
from .tools import AgentTool, ToolExecutionMode

type SchedulerEventSink = Callable[[AgentEvent], None | Awaitable[None]]


async def _emit(sink: SchedulerEventSink | None, event: AgentEvent) -> None:
    if sink is None:
        return
    result = sink(event)
    if inspect.isawaitable(result):
        await result


async def schedule_tool_calls(
    tool_calls: Sequence[ToolCall],
    assistant_message: AssistantMessage,
    context: AgentContext,
    tools: Sequence[AgentTool[Any, Any]],
    *,
    execution_mode: ToolExecutionMode,
    before_tool_call: BeforeToolCallHook | None = None,
    after_tool_call: AfterToolCallHook | None = None,
    abort_event: asyncio.Event | None = None,
    event_sink: SchedulerEventSink | None = None,
    clock: Callable[[], int],
) -> tuple[ToolCallOutcome, ...]:
    force_sequential = execution_mode == "sequential" or any(
        tool.execution_mode == "sequential"
        for call in tool_calls
        for tool in tools
        if tool.name == call.name
    )
    if force_sequential:
        outcomes: list[ToolCallOutcome] = []
        for tool_call in tool_calls:
            outcomes.append(
                await execute_tool_call(
                    tool_call,
                    assistant_message,
                    context,
                    tools,
                    before_tool_call=before_tool_call,
                    after_tool_call=after_tool_call,
                    abort_event=abort_event,
                    event_sink=event_sink,
                    timestamp=clock(),
                )
            )
        return tuple(outcomes)

    preparation_gate = asyncio.Lock()
    tasks = tuple(
        asyncio.create_task(
            execute_tool_call(
                tool_call,
                assistant_message,
                context,
                tools,
                before_tool_call=before_tool_call,
                after_tool_call=after_tool_call,
                abort_event=abort_event,
                event_sink=event_sink,
                timestamp=clock(),
                _preparation_gate=preparation_gate,
                _emit_message_events=False,
            )
        )
        for tool_call in tool_calls
    )
    parallel_outcomes = tuple(await asyncio.gather(*tasks))
    for outcome in parallel_outcomes:
        await _emit(event_sink, MessageStartEvent(message=outcome.message))
        await _emit(event_sink, MessageEndEvent(message=outcome.message))
    return parallel_outcomes


__all__ = ["SchedulerEventSink", "schedule_tool_calls"]
