from __future__ import annotations

import asyncio

from pydantic import BaseModel

from pi_agent.context import AgentContext
from pi_agent.tool_pipeline import (
    AfterToolCallContext,
    AfterToolCallResult,
    BeforeToolCallContext,
    BeforeToolCallResult,
    execute_tool_call,
)
from pi_agent.tools import (
    AgentTool,
    AgentToolExecute,
    AgentToolResult,
    AgentToolUpdateCallback,
    PrepareArguments,
)
from pi_ai import JsonObject, TextContent, ToolCall, ToolResultMessage, fake_assistant_message


class ValueArgs(BaseModel):
    value: int


def _tool(
    execute: AgentToolExecute[ValueArgs, dict[str, int]],
    *,
    prepare_arguments: PrepareArguments | None = None,
) -> AgentTool[ValueArgs, dict[str, int]]:
    return AgentTool(
        name="value",
        label="Value",
        description="Return a value",
        parameter_type=ValueArgs,
        execute=execute,
        prepare_arguments=prepare_arguments,
    )


def _call(arguments: JsonObject | None = None) -> ToolCall:
    return ToolCall(id="call-1", name="value", arguments=arguments or {"value": 3})


def _result_text(message: ToolResultMessage) -> str:
    assert isinstance(message.content[0], TextContent)
    return message.content[0].text


def test_pipeline_prepares_validates_hooks_executes_and_finalizes_in_order() -> None:
    async def scenario() -> None:
        order: list[str] = []

        def prepare(raw: object) -> object:
            order.append("prepare")
            assert raw == {"legacy": 3}
            return {"value": 3}

        async def execute(
            tool_call_id: str,
            params: ValueArgs,
            abort_event: asyncio.Event | None,
            on_update: AgentToolUpdateCallback[dict[str, int]] | None,
        ) -> AgentToolResult[dict[str, int]]:
            order.append("execute")
            assert tool_call_id == "call-1"
            assert params.value == 3
            assert abort_event is None
            assert on_update is not None
            return AgentToolResult(
                content=(TextContent(text="3"),),
                details={"value": 3},
            )

        async def before(context: BeforeToolCallContext) -> BeforeToolCallResult | None:
            order.append("before")
            return None

        async def after(context: AfterToolCallContext) -> AfterToolCallResult:
            order.append("after")
            return AfterToolCallResult(content=(TextContent(text="final"),))

        outcome = await execute_tool_call(
            _call({"legacy": 3}),
            fake_assistant_message((_call({"legacy": 3}),), stop_reason="toolUse"),
            AgentContext(system_prompt="", messages=()),
            (_tool(execute, prepare_arguments=prepare),),
            before_tool_call=before,
            after_tool_call=after,
            timestamp=10,
        )

        assert order == ["prepare", "before", "execute", "after"]
        assert outcome.is_error is False
        assert outcome.message.content == (TextContent(text="final"),)
        assert outcome.message.details == {"value": 3}
        assert outcome.message.timestamp == 10

    asyncio.run(scenario())


def test_unknown_invalid_and_execution_errors_become_error_messages() -> None:
    async def scenario() -> None:
        async def explode(
            tool_call_id: str,
            params: ValueArgs,
            abort_event: asyncio.Event | None,
            on_update: AgentToolUpdateCallback[dict[str, int]] | None,
        ) -> AgentToolResult[dict[str, int]]:
            raise RuntimeError("boom")

        assistant = fake_assistant_message((_call(),), stop_reason="toolUse")
        context = AgentContext(system_prompt="", messages=())
        tool = _tool(explode)

        unknown = await execute_tool_call(
            ToolCall(id="missing", name="missing", arguments={}),
            assistant,
            context,
            (),
            timestamp=1,
        )
        invalid = await execute_tool_call(
            _call({"value": "3"}), assistant, context, (tool,), timestamp=2
        )
        failed = await execute_tool_call(_call(), assistant, context, (tool,), timestamp=3)

        assert unknown.is_error and "not found" in _result_text(unknown.message)
        assert invalid.is_error and "validation" in _result_text(invalid.message).lower()
        assert failed.is_error and _result_text(failed.message) == "boom"

    asyncio.run(scenario())


def test_before_hook_can_block_without_calling_the_tool() -> None:
    async def scenario() -> None:
        executed = False

        async def execute(
            tool_call_id: str,
            params: ValueArgs,
            abort_event: asyncio.Event | None,
            on_update: AgentToolUpdateCallback[dict[str, int]] | None,
        ) -> AgentToolResult[dict[str, int]]:
            nonlocal executed
            executed = True
            return AgentToolResult(content=(), details={})

        async def before(context: BeforeToolCallContext) -> BeforeToolCallResult:
            return BeforeToolCallResult(block=True, reason="denied", terminate=True)

        outcome = await execute_tool_call(
            _call(),
            fake_assistant_message((_call(),), stop_reason="toolUse"),
            AgentContext(system_prompt="", messages=()),
            (_tool(execute),),
            before_tool_call=before,
            timestamp=4,
        )

        assert executed is False
        assert outcome.is_error is True
        assert outcome.terminate is True
        assert outcome.message.content == (TextContent(text="denied"),)

    asyncio.run(scenario())
