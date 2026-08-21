"""Stateful facade around the low-level agent loop."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Iterable, Sequence
from typing import Any

from pi_ai import (
    AssistantMessage,
    Model,
    ModelThinkingLevel,
    StreamFunction,
    TextContent,
    UserMessage,
)

from .cancellation import CancellationController, RunCancellation
from .context import AgentContext, ConvertToLlm, TransformContext
from .events import (
    AgentEvent,
    MessageEndEvent,
    MessageUpdateEvent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
    ToolExecutionUpdateEvent,
)
from .loop import AgentLoopConfig, run_agent_loop
from .messages import AgentMessage, default_convert_to_llm
from .queues import PendingMessageQueue, QueueMode
from .state import AgentState
from .tool_pipeline import AfterToolCallHook, BeforeToolCallHook
from .tools import AgentTool, ToolExecutionMode


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


class Agent:
    def __init__(
        self,
        *,
        model: Model,
        stream_function: StreamFunction,
        system_prompt: str = "",
        thinking_level: ModelThinkingLevel = "off",
        tools: Iterable[AgentTool[Any, Any]] = (),
        messages: Iterable[AgentMessage] = (),
        transform_context: TransformContext | None = None,
        convert_to_llm: ConvertToLlm = default_convert_to_llm,
        before_tool_call: BeforeToolCallHook | None = None,
        after_tool_call: AfterToolCallHook | None = None,
        steering_mode: QueueMode = "one-at-a-time",
        follow_up_mode: QueueMode = "one-at-a-time",
        tool_execution: ToolExecutionMode = "parallel",
        max_turns: int = 100,
        clock: Callable[[], int] | None = None,
    ) -> None:
        self._model = model
        self._stream_function = stream_function
        self._system_prompt = system_prompt
        self._thinking_level: ModelThinkingLevel = thinking_level
        self._tools = tuple(tools)
        self._messages = list(messages)
        self._transform_context = transform_context
        self._convert_to_llm = convert_to_llm
        self._before_tool_call = before_tool_call
        self._after_tool_call = after_tool_call
        self._tool_execution: ToolExecutionMode = tool_execution
        self._max_turns = max_turns
        self._clock: Callable[[], int] = clock or _now_ms
        self._steering_queue = PendingMessageQueue(mode=steering_mode)
        self._follow_up_queue = PendingMessageQueue(mode=follow_up_mode)
        self._cancellation = CancellationController()
        self._is_streaming = False
        self._streaming_message: AssistantMessage | None = None
        self._pending_tool_calls: set[str] = set()
        self._error_message: str | None = None

    @property
    def state(self) -> AgentState:
        return AgentState(
            system_prompt=self._system_prompt,
            model=self._model,
            thinking_level=self._thinking_level,
            tools=self._tools,
            messages=self._messages,
            is_streaming=self._is_streaming,
            streaming_message=self._streaming_message,
            pending_tool_calls=self._pending_tool_calls,
            error_message=self._error_message,
        )

    def steer(self, message: AgentMessage) -> None:
        self._steering_queue.enqueue(message)

    def follow_up(self, message: AgentMessage) -> None:
        self._follow_up_queue.enqueue(message)

    def clear_steering_queue(self) -> None:
        self._steering_queue.clear()

    def clear_follow_up_queue(self) -> None:
        self._follow_up_queue.clear()

    def clear_all_queues(self) -> None:
        self.clear_steering_queue()
        self.clear_follow_up_queue()

    @property
    def has_queued_messages(self) -> bool:
        return self._steering_queue.has_items or self._follow_up_queue.has_items

    @property
    def signal(self) -> asyncio.Event | None:
        return self._cancellation.signal

    def abort(self) -> None:
        self._cancellation.abort()

    async def prompt(self, prompt: str | AgentMessage | Sequence[AgentMessage]) -> None:
        if self._is_streaming:
            raise RuntimeError(
                "Agent is already processing a prompt. Use steer() or follow_up() to queue "
                "messages, or wait for completion."
            )
        prompts = self._normalize_prompt(prompt)
        run = self._cancellation.begin()
        self._is_streaming = True
        self._streaming_message = None
        self._error_message = None
        try:
            result = await run_agent_loop(
                prompts,
                AgentContext(
                    system_prompt=self._system_prompt,
                    messages=self._messages,
                    tools=self._tools,
                ),
                AgentLoopConfig(
                    model=self._model,
                    stream_function=self._stream_function,
                    transform_context=self._transform_context,
                    convert_to_llm=self._convert_to_llm,
                    event_sink=lambda event: self._process_event(run, event),
                    abort_event=run.abort_event,
                    before_tool_call=self._before_tool_call,
                    after_tool_call=self._after_tool_call,
                    max_turns=self._max_turns,
                    tool_execution=self._tool_execution,
                    get_steering_messages=self._drain_steering,
                    get_follow_up_messages=self._drain_follow_up,
                    clock=self._clock,
                ),
            )
            self._messages.extend(result)
        finally:
            self._is_streaming = False
            self._streaming_message = None
            self._pending_tool_calls.clear()
            self._cancellation.finish(run)

    def _normalize_prompt(
        self, prompt: str | AgentMessage | Sequence[AgentMessage]
    ) -> tuple[AgentMessage, ...]:
        if isinstance(prompt, str):
            return (UserMessage(content=(TextContent(text=prompt),), timestamp=self._clock()),)
        if isinstance(prompt, Sequence):
            return tuple(prompt)
        return (prompt,)

    async def _drain_steering(self) -> tuple[AgentMessage, ...]:
        return self._steering_queue.drain()

    async def _drain_follow_up(self) -> tuple[AgentMessage, ...]:
        return self._follow_up_queue.drain()

    def _process_event(self, run: RunCancellation, event: AgentEvent) -> None:
        if isinstance(event, MessageUpdateEvent | ToolExecutionUpdateEvent):
            if not self._cancellation.accepts_update(run):
                return
        elif not self._cancellation.accepts(run):
            return
        if isinstance(event, MessageUpdateEvent):
            self._streaming_message = event.message
        elif isinstance(event, MessageEndEvent) and isinstance(event.message, AssistantMessage):
            self._streaming_message = None
            self._error_message = event.message.error_message
        elif isinstance(event, ToolExecutionStartEvent):
            self._pending_tool_calls.add(event.tool_call_id)
        elif isinstance(event, ToolExecutionEndEvent):
            self._pending_tool_calls.discard(event.tool_call_id)


__all__ = ["Agent"]
