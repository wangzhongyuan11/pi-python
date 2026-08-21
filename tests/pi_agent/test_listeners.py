from __future__ import annotations

import asyncio
from collections.abc import Sequence

import pytest

import pi_agent
from pi_agent.agent import Agent
from pi_agent.events import AgentEndEvent, AgentEvent, AgentStartEvent, MessageEndEvent
from pi_agent.messages import AgentMessage
from pi_agent.stream_function import set_default_stream_function
from pi_ai import FakeProvider, fake_assistant_message, fake_model

EXPECTED_EXPORTS = {
    "AfterToolCallContext",
    "AfterToolCallHook",
    "AfterToolCallResult",
    "Agent",
    "AgentContext",
    "AgentEndEvent",
    "AgentEvent",
    "AgentEventListener",
    "AgentEventSequence",
    "AgentEventSink",
    "AgentLoopConfig",
    "AgentMessage",
    "AgentStartEvent",
    "AgentState",
    "AgentTool",
    "AgentToolExecute",
    "AgentToolResult",
    "AgentToolUpdateCallback",
    "BRANCH_SUMMARY_PREFIX",
    "BRANCH_SUMMARY_SUFFIX",
    "BashExecutionMessage",
    "BeforeToolCallContext",
    "BeforeToolCallHook",
    "BeforeToolCallResult",
    "BranchSummaryMessage",
    "COMPACTION_SUMMARY_PREFIX",
    "COMPACTION_SUMMARY_SUFFIX",
    "CompactionSummaryMessage",
    "ConvertToLlm",
    "CustomMessage",
    "MessageEndEvent",
    "MessageStartEvent",
    "MessageUpdateEvent",
    "PendingMessageSource",
    "PrepareArguments",
    "QueueMode",
    "ToolCallOutcome",
    "ToolEventSink",
    "ToolExecutionEndEvent",
    "ToolExecutionMode",
    "ToolExecutionStartEvent",
    "ToolExecutionUpdateEvent",
    "TransformContext",
    "TurnEndEvent",
    "TurnStartEvent",
    "__version__",
    "bash_execution_to_text",
    "build_llm_context",
    "default_convert_to_llm",
    "execute_tool_call",
    "fail_tool_call",
    "run_agent_loop",
    "set_default_stream_function",
}


def test_sync_and_async_listeners_run_in_subscription_order() -> None:
    async def scenario() -> None:
        observed: list[str] = []
        signals: list[asyncio.Event] = []

        def first(event: AgentEvent, signal: asyncio.Event) -> None:
            if isinstance(event, AgentStartEvent):
                observed.append("sync")
                signals.append(signal)

        async def second(event: AgentEvent, signal: asyncio.Event) -> None:
            if isinstance(event, AgentStartEvent):
                observed.append("async-start")
                signals.append(signal)
                await asyncio.sleep(0)
                observed.append("async-end")

        provider = FakeProvider([fake_assistant_message("first"), fake_assistant_message("second")])
        agent = Agent(model=fake_model(), stream_function=provider.stream)
        unsubscribe = agent.subscribe(first)
        agent.subscribe(second)

        await agent.prompt("one")

        assert observed == ["sync", "async-start", "async-end"]
        assert signals == [signals[0], signals[0]]
        assert signals[0].is_set() is False

        unsubscribe()
        observed.clear()
        await agent.prompt("two")

        assert observed == ["async-start", "async-end"]

    asyncio.run(scenario())


def test_wait_for_idle_waits_for_agent_end_listener_and_state_reduction() -> None:
    async def scenario() -> None:
        listener_entered = asyncio.Event()
        release_listener = asyncio.Event()
        state_was_reduced: list[bool] = []

        provider = FakeProvider([fake_assistant_message("done")])
        agent = Agent(model=fake_model(), stream_function=provider.stream)

        async def listener(event: AgentEvent, _signal: asyncio.Event) -> None:
            if isinstance(event, MessageEndEvent):
                state_was_reduced.append(event.message in agent.state.messages)
            if isinstance(event, AgentEndEvent):
                listener_entered.set()
                await release_listener.wait()

        agent.subscribe(listener)
        active = asyncio.create_task(agent.prompt("start"))
        await listener_entered.wait()
        idle = asyncio.create_task(agent.wait_for_idle())
        await asyncio.sleep(0)

        assert not idle.done()
        assert agent.state.is_streaming
        assert state_was_reduced and all(state_was_reduced)

        release_listener.set()
        await active
        await idle

        assert not agent.state.is_streaming

    asyncio.run(scenario())


def test_wait_for_idle_awaitable_is_bound_to_the_run_at_call_time() -> None:
    async def scenario() -> None:
        first_end_entered = asyncio.Event()
        release_first_end = asyncio.Event()
        second_transform_entered = asyncio.Event()
        release_second_transform = asyncio.Event()
        transform_calls = 0
        agent_end_calls = 0

        async def transform(messages: Sequence[AgentMessage]) -> Sequence[AgentMessage]:
            nonlocal transform_calls
            transform_calls += 1
            if transform_calls == 2:
                second_transform_entered.set()
                await release_second_transform.wait()
            return messages

        provider = FakeProvider([fake_assistant_message("first"), fake_assistant_message("second")])
        agent = Agent(
            model=fake_model(),
            stream_function=provider.stream,
            transform_context=transform,
        )

        async def listener(event: AgentEvent, _signal: asyncio.Event) -> None:
            nonlocal agent_end_calls
            if isinstance(event, AgentEndEvent):
                agent_end_calls += 1
                if agent_end_calls == 1:
                    first_end_entered.set()
                    await release_first_end.wait()

        agent.subscribe(listener)
        first_prompt = asyncio.create_task(agent.prompt("one"))
        await first_end_entered.wait()
        first_idle = agent.wait_for_idle()

        release_first_end.set()
        await first_prompt
        second_prompt = asyncio.create_task(agent.prompt("two"))
        await second_transform_entered.wait()

        waited_for_second_run = False
        try:
            await asyncio.wait_for(first_idle, timeout=0.01)
        except TimeoutError:
            waited_for_second_run = True
        finally:
            release_second_transform.set()
            await second_prompt

        assert not waited_for_second_run

    asyncio.run(scenario())


def test_root_exports_and_default_stream_function_are_stable() -> None:
    async def scenario() -> None:
        provider = FakeProvider([fake_assistant_message("done")])
        set_default_stream_function(provider.stream)
        try:
            agent = Agent(model=fake_model())
            await agent.prompt("start")
            assert provider.call_count == 1
        finally:
            set_default_stream_function(None)

        with pytest.raises(RuntimeError, match="No default stream function configured"):
            Agent(model=fake_model())

    assert set(pi_agent.__all__) == EXPECTED_EXPORTS
    for name in EXPECTED_EXPORTS:
        assert hasattr(pi_agent, name), name
    asyncio.run(scenario())
