"""P15.5/1.1.0 gap closure: tool execution records durationMs.

The duration is emitted on tool_execution_end and persisted in the tool
result's details so it survives session reload.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic import BaseModel

from pi_ai import FakeProvider, ToolCall, fake_assistant_message


class _Args(BaseModel):
    pass


def _tool():
    from pi_agent import AgentTool, AgentToolResult
    from pi_ai import TextContent

    async def _execute(_call_id, _params, _abort, _update):
        await asyncio.sleep(0.06)
        return AgentToolResult(content=(TextContent(text="done"),), details=None)

    return AgentTool(
        name="slow_tool",
        label="Slow",
        description="sleeps briefly",
        parameter_type=_Args,
        execute=_execute,
    )


def _provider():
    return FakeProvider(
        [
            fake_assistant_message(
                ToolCall(id="d1", name="slow_tool", arguments={}), stop_reason="toolUse"
            ),
            fake_assistant_message("finished"),
        ]
    )


def test_tool_execution_end_records_duration_ms(tmp_path: Path) -> None:
    from pi_coding_agent.model_runtime import ModelRuntime
    from pi_coding_agent.sdk import CreateAgentSessionOptions, create_agent_session

    durations: list[object] = []
    provider = _provider()

    async def scenario() -> None:
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=ModelRuntime(provider=provider, model=provider.models[0]),
                tools=(_tool(),),
            )
        )
        try:
            created.services.extensions.register_hook(
                "tool_execution_end",
                lambda event: durations.append(getattr(event, "duration_ms", "MISSING")),
            )
            await created.session.prompt("run it")
        finally:
            await created.close()

    asyncio.run(scenario())
    assert durations and durations[0] != "MISSING", "tool_execution_end must carry duration_ms"
    assert isinstance(durations[0], int) and durations[0] >= 40


def test_duration_ms_is_persisted_in_tool_result_details(tmp_path: Path) -> None:
    from pi_coding_agent.model_runtime import ModelRuntime
    from pi_coding_agent.sdk import CreateAgentSessionOptions, create_agent_session
    from pi_coding_agent.session.catalog import open_session

    provider = _provider()

    async def scenario() -> Path:
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=ModelRuntime(provider=provider, model=provider.models[0]),
                tools=(_tool(),),
            )
        )
        try:
            await created.session.prompt("run it")
            return created.session.session_manager.path
        finally:
            await created.close()

    path = asyncio.run(scenario())
    assert path is not None
    manager = open_session(path)
    tool_results = [
        entry
        for entry in manager.entries
        if isinstance(entry.message, dict) and entry.message.get("role") == "toolResult"
    ]
    assert tool_results, "session must contain a tool result entry"
    details = tool_results[-1].message.get("details")
    assert isinstance(details, dict) and isinstance(details.get("durationMs"), int)
