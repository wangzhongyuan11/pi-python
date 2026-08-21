"""Low-level asynchronous agent loop."""

from __future__ import annotations

import asyncio
import inspect
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

type AgentEventSink = Callable[[AgentEvent], None | Awaitable[None]]


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentLoopConfig:
    model: Model
    stream_function: StreamFunction
    transform_context: TransformContext | None = None
    convert_to_llm: ConvertToLlm = default_convert_to_llm
    event_sink: AgentEventSink | None = None
    abort_event: asyncio.Event | None = None


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

    assistant = await _stream_assistant(
        AgentContext(
            system_prompt=context.system_prompt,
            messages=current_messages,
            tools=context.tools,
        ),
        config,
        emitter,
    )
    current_messages.append(assistant)
    new_messages.append(assistant)

    await emitter.emit(TurnEndEvent(message=assistant, tool_results=()))
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
