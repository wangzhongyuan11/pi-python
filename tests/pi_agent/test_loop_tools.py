from __future__ import annotations

import asyncio

from pydantic import BaseModel

from pi_agent.context import AgentContext
from pi_agent.loop import AgentLoopConfig, run_agent_loop
from pi_agent.tools import AgentTool, AgentToolResult, AgentToolUpdateCallback
from pi_ai import (
    AssistantMessage,
    FakeProvider,
    TextContent,
    ToolCall,
    ToolResultMessage,
    UserMessage,
    fake_assistant_message,
    fake_model,
)


class EchoArgs(BaseModel):
    value: str


def _user() -> UserMessage:
    return UserMessage(content=(TextContent(text="start"),), timestamp=1)


def _tool(executed: list[str], *, terminate: bool = False) -> AgentTool[EchoArgs, dict[str, str]]:
    async def execute(
        tool_call_id: str,
        params: EchoArgs,
        abort_event: asyncio.Event | None,
        on_update: AgentToolUpdateCallback[dict[str, str]] | None,
    ) -> AgentToolResult[dict[str, str]]:
        executed.append(params.value)
        return AgentToolResult(
            content=(TextContent(text=params.value),),
            details={"value": params.value},
            terminate=terminate,
        )

    return AgentTool(
        name="echo",
        label="Echo",
        description="Echo a value",
        parameter_type=EchoArgs,
        execute=execute,
    )


def _tool_response(*values: str, timestamp: int = 2) -> AssistantMessage:
    return fake_assistant_message(
        tuple(
            ToolCall(id=f"call-{index}", name="echo", arguments={"value": value})
            for index, value in enumerate(values, start=1)
        ),
        stop_reason="toolUse",
        timestamp=timestamp,
    )


def test_loop_executes_tools_then_calls_provider_again_with_results() -> None:
    async def scenario() -> None:
        executed: list[str] = []
        first = _tool_response("one")
        final = fake_assistant_message("finished", timestamp=4)
        provider = FakeProvider([first, final])

        result = await run_agent_loop(
            (_user(),),
            AgentContext(system_prompt="system", messages=(), tools=(_tool(executed),)),
            AgentLoopConfig(
                model=fake_model(),
                stream_function=provider.stream,
                clock=lambda: 3,
            ),
        )

        assert executed == ["one"]
        assert provider.call_count == 2
        assert [message.role for message in result] == [
            "user",
            "assistant",
            "toolResult",
            "assistant",
        ]
        tool_result = result[2]
        assert isinstance(tool_result, ToolResultMessage)
        assert tool_result.tool_call_id == "call-1"
        assert provider.calls[1][1].messages[-1] == tool_result

    asyncio.run(scenario())


def test_multiple_tool_calls_are_appended_in_model_order() -> None:
    async def scenario() -> None:
        executed: list[str] = []
        provider = FakeProvider([_tool_response("first", "second"), fake_assistant_message("done")])

        result = await run_agent_loop(
            (_user(),),
            AgentContext(system_prompt="", messages=(), tools=(_tool(executed),)),
            AgentLoopConfig(model=fake_model(), stream_function=provider.stream, clock=lambda: 5),
        )

        tool_results = [message for message in result if isinstance(message, ToolResultMessage)]
        assert executed == ["first", "second"]
        assert [message.tool_call_id for message in tool_results] == ["call-1", "call-2"]

    asyncio.run(scenario())


def test_max_turns_stops_an_unbounded_tool_chain() -> None:
    async def scenario() -> None:
        executed: list[str] = []
        provider = FakeProvider([_tool_response("one"), _tool_response("two", timestamp=4)])

        result = await run_agent_loop(
            (_user(),),
            AgentContext(system_prompt="", messages=(), tools=(_tool(executed),)),
            AgentLoopConfig(
                model=fake_model(),
                stream_function=provider.stream,
                max_turns=2,
                clock=lambda: 6,
            ),
        )

        assert provider.call_count == 2
        assert executed == ["one", "two"]
        assert isinstance(result[-1], ToolResultMessage)

    asyncio.run(scenario())


def test_all_terminate_results_stop_without_another_provider_call() -> None:
    async def scenario() -> None:
        executed: list[str] = []
        provider = FakeProvider([_tool_response("stop")])

        result = await run_agent_loop(
            (_user(),),
            AgentContext(system_prompt="", messages=(), tools=(_tool(executed, terminate=True),)),
            AgentLoopConfig(model=fake_model(), stream_function=provider.stream, clock=lambda: 7),
        )

        assert provider.call_count == 1
        assert executed == ["stop"]
        assert isinstance(result[-1], ToolResultMessage)

    asyncio.run(scenario())


def test_length_tool_calls_are_failed_without_execution() -> None:
    async def scenario() -> None:
        executed: list[str] = []
        truncated = _tool_response("unsafe")
        truncated = AssistantMessage(
            content=truncated.content,
            api=truncated.api,
            provider=truncated.provider,
            model=truncated.model,
            usage=truncated.usage,
            stop_reason="length",
            timestamp=truncated.timestamp,
        )
        provider = FakeProvider([truncated, fake_assistant_message("recovered")])

        result = await run_agent_loop(
            (_user(),),
            AgentContext(system_prompt="", messages=(), tools=(_tool(executed),)),
            AgentLoopConfig(model=fake_model(), stream_function=provider.stream, clock=lambda: 8),
        )

        tool_result = result[2]
        assert executed == []
        assert isinstance(tool_result, ToolResultMessage)
        assert tool_result.is_error is True
        assert isinstance(tool_result.content[0], TextContent)
        assert "output token limit" in tool_result.content[0].text

    asyncio.run(scenario())
