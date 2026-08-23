from __future__ import annotations

import asyncio
from dataclasses import replace

from pydantic import BaseModel

from pi_agent.agent import Agent
from pi_agent.cancellation import CancellationController
from pi_agent.tools import AgentTool, AgentToolResult, AgentToolUpdateCallback
from pi_ai import (
    AssistantMessage,
    AssistantMessageStartEvent,
    AssistantStream,
    Context,
    ErrorEvent,
    FakeProvider,
    Model,
    StreamOptions,
    TextContent,
    TextDeltaEvent,
    TextStartEvent,
    ToolCall,
    fake_assistant_message,
    fake_model,
)


class NoArgs(BaseModel):
    pass


def test_generation_rejects_stale_and_aborted_updates() -> None:
    controller = CancellationController()
    first = controller.begin()

    assert controller.accepts(first)
    assert controller.accepts_update(first)

    controller.abort()

    assert controller.accepts(first)
    assert not controller.accepts_update(first)

    controller.finish(first)
    second = controller.begin()

    assert not controller.accepts(first)
    assert controller.accepts(second)


def test_abort_discards_provider_updates_but_keeps_aborted_terminal_message() -> None:
    async def scenario() -> None:
        late_update_sent = asyncio.Event()
        release_terminal = asyncio.Event()
        producer_tasks: set[asyncio.Task[None]] = set()

        def stream(
            model: Model,
            context: Context,
            options: StreamOptions | None = None,
        ) -> AssistantStream:
            del model, context
            assistant_stream = AssistantStream()

            async def produce() -> None:
                initial = replace(
                    fake_assistant_message(""),
                    content=(),
                    stop_reason="pending",
                )
                assistant_stream.push(AssistantMessageStartEvent(partial=initial))
                assert options is not None
                assert options.abort_event is not None
                await options.abort_event.wait()

                late = replace(initial, content=(TextContent(text="late"),))
                assistant_stream.push(TextStartEvent(content_index=0, partial=initial))
                assistant_stream.push(TextDeltaEvent(content_index=0, delta="late", partial=late))
                late_update_sent.set()
                await release_terminal.wait()

                aborted = replace(
                    late,
                    stop_reason="aborted",
                    error_message="Request was aborted",
                )
                assistant_stream.push(ErrorEvent(reason="aborted", error=aborted))

            task = asyncio.create_task(produce())
            producer_tasks.add(task)
            task.add_done_callback(producer_tasks.discard)
            return assistant_stream

        agent = Agent(model=fake_model(), stream_function=stream)
        active = asyncio.create_task(agent.prompt("start"))
        while agent.signal is None:
            await asyncio.sleep(0)

        agent.abort()
        await late_update_sent.wait()

        streaming = agent.state.streaming_message
        assert streaming is not None
        assert streaming.content == ()

        release_terminal.set()
        await active

        assert agent.signal is None
        assert agent.state.messages[-1].role == "assistant"
        assert agent.state.messages[-1].stop_reason == "aborted"
        assert agent.state.error_message == "Request was aborted"
        if producer_tasks:
            await asyncio.gather(*producer_tasks)

    asyncio.run(scenario())


def test_abort_signal_reaches_tool_and_stops_the_following_provider_turn() -> None:
    async def scenario() -> None:
        tool_started = asyncio.Event()
        tool_observed_abort = asyncio.Event()

        async def execute(
            _tool_call_id: str,
            _params: NoArgs,
            abort_event: asyncio.Event | None,
            on_update: AgentToolUpdateCallback[dict[str, bool]] | None,
        ) -> AgentToolResult[dict[str, bool]]:
            assert abort_event is not None
            tool_started.set()
            await abort_event.wait()
            tool_observed_abort.set()
            if on_update is not None:
                on_update(
                    AgentToolResult(
                        content=(TextContent(text="late"),),
                        details={"late": True},
                    )
                )
            return AgentToolResult(
                content=(TextContent(text="cancelled"),),
                details={"late": False},
            )

        tool = AgentTool(
            name="wait",
            label="Wait",
            description="Wait for cancellation",
            parameter_type=NoArgs,
            execute=execute,
        )
        provider = FakeProvider(
            [
                fake_assistant_message(
                    ToolCall(id="call-1", name="wait", arguments={}),
                    stop_reason="toolUse",
                )
            ]
        )
        agent = Agent(
            model=fake_model(),
            stream_function=provider.stream,
            tools=(tool,),
        )

        active = asyncio.create_task(agent.prompt("start"))
        await tool_started.wait()
        signal = agent.signal
        assert signal is not None

        agent.abort()
        await active

        assert signal.is_set()
        assert tool_observed_abort.is_set()
        assert provider.call_count == 2
        last_message = agent.state.messages[-1]
        assert isinstance(last_message, AssistantMessage)
        assert last_message.stop_reason == "aborted"
        assert agent.state.pending_tool_calls == frozenset()

    asyncio.run(scenario())
