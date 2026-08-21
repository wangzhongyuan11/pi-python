"""Prepare, validate, execute, and finalize one model tool call."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, cast

from pi_ai import (
    AssistantMessage,
    ImageContent,
    JsonValue,
    TextContent,
    ToolCall,
    ToolResultMessage,
    Usage,
)

from .context import AgentContext
from .events import (
    AgentEvent,
    MessageEndEvent,
    MessageStartEvent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
    ToolExecutionUpdateEvent,
)
from .tools import AgentTool, AgentToolResult

_UNSET = object()
type ToolEventSink = Callable[[AgentEvent], None | Awaitable[None]]


@dataclass(frozen=True, slots=True, kw_only=True)
class BeforeToolCallContext:
    assistant_message: AssistantMessage
    tool_call: ToolCall
    args: object
    context: AgentContext


@dataclass(frozen=True, slots=True, kw_only=True)
class BeforeToolCallResult:
    block: bool = False
    reason: str | None = None
    terminate: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class AfterToolCallContext:
    assistant_message: AssistantMessage
    tool_call: ToolCall
    args: object
    result: AgentToolResult[Any]
    is_error: bool
    context: AgentContext


@dataclass(frozen=True, slots=True, kw_only=True)
class AfterToolCallResult:
    content: tuple[TextContent | ImageContent, ...] | None = None
    details: object = _UNSET
    is_error: bool | None = None
    usage: Usage | None = None
    terminate: bool | None = None


type BeforeToolCallHook = Callable[[BeforeToolCallContext], Awaitable[BeforeToolCallResult | None]]
type AfterToolCallHook = Callable[[AfterToolCallContext], Awaitable[AfterToolCallResult | None]]


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolCallOutcome:
    tool_call: ToolCall
    result: AgentToolResult[Any]
    message: ToolResultMessage
    is_error: bool
    terminate: bool


async def _emit(sink: ToolEventSink | None, event: AgentEvent) -> None:
    if sink is None:
        return
    emitted = sink(event)
    if inspect.isawaitable(emitted):
        await emitted


def _error_result(message: str, *, terminate: bool = False) -> AgentToolResult[JsonValue]:
    return AgentToolResult(
        content=(TextContent(text=message),),
        details={},
        terminate=terminate,
    )


async def execute_tool_call(
    tool_call: ToolCall,
    assistant_message: AssistantMessage,
    context: AgentContext,
    tools: Sequence[AgentTool[Any, Any]],
    *,
    before_tool_call: BeforeToolCallHook | None = None,
    after_tool_call: AfterToolCallHook | None = None,
    abort_event: asyncio.Event | None = None,
    event_sink: ToolEventSink | None = None,
    timestamp: int,
) -> ToolCallOutcome:
    await _emit(
        event_sink,
        ToolExecutionStartEvent(
            tool_call_id=tool_call.id,
            tool_name=tool_call.name,
            args=tool_call.arguments,
        ),
    )
    tool = next((candidate for candidate in tools if candidate.name == tool_call.name), None)
    if tool is None:
        return await _finalize_immediate(
            tool_call,
            _error_result(f"Tool {tool_call.name} not found"),
            timestamp,
            event_sink,
        )

    try:
        prepared = tool.prepare_arguments(tool_call.arguments)
        args = tool.validate_arguments(prepared)
        if before_tool_call is not None:
            before = await before_tool_call(
                BeforeToolCallContext(
                    assistant_message=assistant_message,
                    tool_call=tool_call,
                    args=args,
                    context=context,
                )
            )
            if before is not None and before.block:
                return await _finalize_immediate(
                    tool_call,
                    _error_result(
                        before.reason or "Tool execution was blocked",
                        terminate=before.terminate,
                    ),
                    timestamp,
                    event_sink,
                )
        if abort_event is not None and abort_event.is_set():
            return await _finalize_immediate(
                tool_call,
                _error_result("Operation aborted"),
                timestamp,
                event_sink,
            )
    except Exception as error:
        return await _finalize_immediate(
            tool_call,
            _error_result(str(error)),
            timestamp,
            event_sink,
        )

    update_tasks: list[asyncio.Task[None]] = []
    accepting_updates = True

    def on_update(partial_result: AgentToolResult[Any]) -> None:
        if not accepting_updates:
            return
        update_tasks.append(
            asyncio.create_task(
                _emit(
                    event_sink,
                    ToolExecutionUpdateEvent(
                        tool_call_id=tool_call.id,
                        tool_name=tool_call.name,
                        args=tool_call.arguments,
                        partial_result=partial_result,
                    ),
                )
            )
        )

    is_error = False
    try:
        result = await tool.execute(tool_call.id, args, abort_event, on_update)
    except Exception as error:
        result = _error_result(str(error))
        is_error = True
    finally:
        accepting_updates = False
    if update_tasks:
        await asyncio.gather(*update_tasks)

    if after_tool_call is not None:
        try:
            override = await after_tool_call(
                AfterToolCallContext(
                    assistant_message=assistant_message,
                    tool_call=tool_call,
                    args=args,
                    result=result,
                    is_error=is_error,
                    context=context,
                )
            )
            if override is not None:
                result = AgentToolResult(
                    content=override.content if override.content is not None else result.content,
                    details=(
                        cast("Any", override.details)
                        if override.details is not _UNSET
                        else result.details
                    ),
                    usage=override.usage if override.usage is not None else result.usage,
                    added_tool_names=result.added_tool_names,
                    terminate=(
                        override.terminate if override.terminate is not None else result.terminate
                    ),
                )
                if override.is_error is not None:
                    is_error = override.is_error
        except Exception as error:
            result = _error_result(str(error))
            is_error = True

    return await _finalize(tool_call, result, is_error, timestamp, event_sink)


async def fail_tool_call(
    tool_call: ToolCall,
    message: str,
    *,
    timestamp: int,
    event_sink: ToolEventSink | None = None,
) -> ToolCallOutcome:
    await _emit(
        event_sink,
        ToolExecutionStartEvent(
            tool_call_id=tool_call.id,
            tool_name=tool_call.name,
            args=tool_call.arguments,
        ),
    )
    return await _finalize_immediate(
        tool_call,
        _error_result(message),
        timestamp,
        event_sink,
    )


async def _finalize_immediate(
    tool_call: ToolCall,
    result: AgentToolResult[Any],
    timestamp: int,
    event_sink: ToolEventSink | None,
) -> ToolCallOutcome:
    return await _finalize(tool_call, result, True, timestamp, event_sink)


async def _finalize(
    tool_call: ToolCall,
    result: AgentToolResult[Any],
    is_error: bool,
    timestamp: int,
    event_sink: ToolEventSink | None,
) -> ToolCallOutcome:
    await _emit(
        event_sink,
        ToolExecutionEndEvent(
            tool_call_id=tool_call.id,
            tool_name=tool_call.name,
            result=result,
            is_error=is_error,
        ),
    )
    message = ToolResultMessage(
        tool_call_id=tool_call.id,
        tool_name=tool_call.name,
        content=result.content,
        details=cast("JsonValue", result.details),
        usage=result.usage,
        added_tool_names=result.added_tool_names,
        is_error=is_error,
        timestamp=timestamp,
    )
    await _emit(event_sink, MessageStartEvent(message=message))
    await _emit(event_sink, MessageEndEvent(message=message))
    return ToolCallOutcome(
        tool_call=tool_call,
        result=result,
        message=message,
        is_error=is_error,
        terminate=result.terminate,
    )


__all__ = [
    "AfterToolCallContext",
    "AfterToolCallHook",
    "AfterToolCallResult",
    "BeforeToolCallContext",
    "BeforeToolCallHook",
    "BeforeToolCallResult",
    "ToolCallOutcome",
    "ToolEventSink",
    "execute_tool_call",
    "fail_tool_call",
]
