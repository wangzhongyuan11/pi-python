"""Low-level asynchronous agent loop."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from pi_ai import (
    AssistantMessage,
    AssistantMessageStartEvent,
    DoneEvent,
    ErrorEvent,
    Model,
    StreamFunction,
    StreamOptions,
    ToolCall,
    ToolResultMessage,
)

from .context import AgentContext, ConvertToLlm, TransformContext, build_llm_context
from .events import (
    AgentEndEvent,
    AgentEvent,
    AgentEventSequence,
    AgentStartEvent,
    MessageEndEvent,
    MessageStartEvent,
    MessageUpdateEvent,
    TurnEndEvent,
    TurnStartEvent,
)
from .messages import AgentMessage, default_convert_to_llm
from .scheduler import schedule_tool_calls
from .tool_pipeline import (
    AfterToolCallHook,
    BeforeToolCallHook,
    ToolCallOutcome,
    fail_tool_call,
)
from .tools import ToolExecutionMode

type AgentEventSink = Callable[[AgentEvent], None | Awaitable[None]]


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentLoopConfig:
    model: Model
    stream_function: StreamFunction
    transform_context: TransformContext | None = None
    convert_to_llm: ConvertToLlm = default_convert_to_llm
    event_sink: AgentEventSink | None = None
    abort_event: asyncio.Event | None = None
    before_tool_call: BeforeToolCallHook | None = None
    after_tool_call: AfterToolCallHook | None = None
    max_turns: int = 100
    clock: Callable[[], int] = _now_ms
    tool_execution: ToolExecutionMode = "parallel"

    def __post_init__(self) -> None:
        if isinstance(self.max_turns, bool) or self.max_turns <= 0:
            raise ValueError("max_turns must be a positive integer")


class _EventEmitter:
    __slots__ = ("_sequence", "_sink")

    def __init__(self, sink: AgentEventSink | None) -> None:
        self._sink = sink
        self._sequence = AgentEventSequence()

    async def emit(self, event: AgentEvent) -> None:
        self._sequence.accept(event)
        if self._sink is None:
            return
        result = self._sink(event)
        if inspect.isawaitable(result):
            await result


async def run_agent_loop(
    prompts: Sequence[AgentMessage],
    context: AgentContext,
    config: AgentLoopConfig,
) -> tuple[AgentMessage, ...]:
    emitter = _EventEmitter(config.event_sink)
    new_messages = list(prompts)
    current_messages = [*context.messages, *prompts]

    await emitter.emit(AgentStartEvent())
    await emitter.emit(TurnStartEvent())
    for prompt in prompts:
        await emitter.emit(MessageStartEvent(message=prompt))
        await emitter.emit(MessageEndEvent(message=prompt))

    turn = 0
    while True:
        turn += 1
        if turn > 1:
            await emitter.emit(TurnStartEvent())
        turn_context = AgentContext(
            system_prompt=context.system_prompt,
            messages=current_messages,
            tools=context.tools,
        )
        assistant = await _stream_assistant(turn_context, config, emitter)
        current_messages.append(assistant)
        new_messages.append(assistant)

        tool_calls = tuple(
            content for content in assistant.content if isinstance(content, ToolCall)
        )
        tool_results: list[ToolResultMessage] = []
        outcomes: list[ToolCallOutcome] = []
        if assistant.stop_reason == "length":
            for tool_call in tool_calls:
                outcome = await fail_tool_call(
                    tool_call,
                    (
                        f'Tool call "{tool_call.name}" was not executed: the response hit '
                        "the output token limit, so its arguments may be truncated."
                    ),
                    timestamp=config.clock(),
                    event_sink=emitter.emit,
                )
                outcomes.append(outcome)
        else:
            outcomes.extend(
                await schedule_tool_calls(
                    tool_calls,
                    assistant,
                    turn_context,
                    context.tools or (),
                    execution_mode=config.tool_execution,
                    before_tool_call=config.before_tool_call,
                    after_tool_call=config.after_tool_call,
                    abort_event=config.abort_event,
                    event_sink=emitter.emit,
                    clock=config.clock,
                )
            )
        for outcome in outcomes:
            tool_results.append(outcome.message)
            current_messages.append(outcome.message)
            new_messages.append(outcome.message)

        await emitter.emit(TurnEndEvent(message=assistant, tool_results=tuple(tool_results)))
        if assistant.stop_reason in ("error", "aborted"):
            break
        if not tool_calls or turn >= config.max_turns:
            break
        if outcomes and all(outcome.terminate for outcome in outcomes):
            break

    await emitter.emit(AgentEndEvent(messages=tuple(new_messages)))
    return tuple(new_messages)


async def _stream_assistant(
    context: AgentContext,
    config: AgentLoopConfig,
    emitter: _EventEmitter,
) -> AssistantMessage:
    llm_context = await build_llm_context(
        context,
        transform_context=config.transform_context,
        convert_to_llm=config.convert_to_llm,
    )
    stream = config.stream_function(
        config.model,
        llm_context,
        StreamOptions(abort_event=config.abort_event),
    )
    final_message: AssistantMessage | None = None
    started = False

    async for provider_event in stream:
        if isinstance(provider_event, AssistantMessageStartEvent):
            started = True
            await emitter.emit(MessageStartEvent(message=provider_event.partial))
        elif isinstance(provider_event, DoneEvent | ErrorEvent):
            final_message = await stream.result()
            if not started:
                await emitter.emit(MessageStartEvent(message=final_message))
            await emitter.emit(MessageEndEvent(message=final_message))
        else:
            await emitter.emit(
                MessageUpdateEvent(
                    message=provider_event.partial,
                    assistant_message_event=provider_event,
                )
            )

    if final_message is None:
        final_message = await stream.result()
        if not started:
            await emitter.emit(MessageStartEvent(message=final_message))
        await emitter.emit(MessageEndEvent(message=final_message))
    return final_message


__all__ = ["AgentEventSink", "AgentLoopConfig", "run_agent_loop"]
