from __future__ import annotations

import asyncio
from typing import cast

from pydantic import BaseModel

from pi_agent.context import AgentContext
from pi_agent.events import AgentEvent, MessageEndEvent, ToolExecutionEndEvent
from pi_agent.loop import AgentLoopConfig, run_agent_loop
from pi_agent.tools import AgentTool, AgentToolResult, AgentToolUpdateCallback
from pi_ai import (
    FakeProvider,
    JsonObject,
    TextContent,
    ToolCall,
    ToolResultMessage,
    UserMessage,
    fake_assistant_message,
    fake_model,
)


class DelayArgs(BaseModel):
    name: str


def test_parallel_completion_is_visible_but_results_keep_model_order() -> None:
    async def scenario() -> None:
        release_first = asyncio.Event()
        prepared: list[str] = []

        def prepare(raw: object) -> object:
            prepared_args = cast("JsonObject", raw)
            prepared.append(str(prepared_args["name"]))
            return prepared_args

        async def execute(
            tool_call_id: str,
            params: DelayArgs,
            abort_event: asyncio.Event | None,
            on_update: AgentToolUpdateCallback[dict[str, str]] | None,
        ) -> AgentToolResult[dict[str, str]]:
            if params.name == "first":
                await release_first.wait()
            else:
                release_first.set()
            return AgentToolResult(
                content=(TextContent(text=params.name),),
                details={"name": params.name},
            )

        tool = AgentTool(
            name="delay",
            label="Delay",
            description="Complete in a controlled order",
            parameter_type=DelayArgs,
            execute=execute,
            prepare_arguments=prepare,
        )
        tool_turn = fake_assistant_message(
            (
                ToolCall(id="call-first", name="delay", arguments={"name": "first"}),
                ToolCall(id="call-second", name="delay", arguments={"name": "second"}),
            ),
            stop_reason="toolUse",
        )
        provider = FakeProvider([tool_turn, fake_assistant_message("done")])
        events: list[AgentEvent] = []

        result = await run_agent_loop(
            (UserMessage(content="go", timestamp=1),),
            AgentContext(system_prompt="", messages=(), tools=(tool,)),
            AgentLoopConfig(
                model=fake_model(),
                stream_function=provider.stream,
                event_sink=events.append,
                tool_execution="parallel",
                clock=lambda: 2,
            ),
        )

        completion_order = [
            event.tool_call_id for event in events if isinstance(event, ToolExecutionEndEvent)
        ]
        message_order = [
            event.message.tool_call_id
            for event in events
            if isinstance(event, MessageEndEvent) and isinstance(event.message, ToolResultMessage)
        ]
        persisted_order = [
            message.tool_call_id for message in result if isinstance(message, ToolResultMessage)
        ]

        assert completion_order == ["call-second", "call-first"]
        assert prepared == ["first", "second"]
        assert message_order == ["call-first", "call-second"]
        assert persisted_order == ["call-first", "call-second"]

    asyncio.run(scenario())
