"""Historical defect regressions driven through the real product session."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path

from pydantic import BaseModel

from pi_agent import AgentTool, AgentToolResult
from pi_ai import (
    FakeProvider,
    TextContent,
    ToolCall,
    Usage,
    UsageCost,
    fake_assistant_message,
    fake_model,
)
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.ports import ResourceRoot
from pi_coding_agent.sdk import CreateAgentSessionOptions, create_agent_session
from pi_coding_agent.services import ServiceOverrides
from pi_coding_agent.session.manager import SessionManager

INSERT_EXTENSION_MANIFEST = '{"name":"insert","version":"1.0.0","entry":"main.py"}'
INSERT_EXTENSION_MAIN = (
    "def activate(api):\n"
    "    def on_start(event):\n"
    "        api.send_message('inserted', 'inserted-during-tool')\n"
    "    api.on('tool_execution_start', on_start)\n"
    "    return lambda: None\n"
)


class EmptyArgs(BaseModel):
    pass


def _usage(total: int) -> Usage:
    return Usage(
        input=total,
        output=0,
        cache_read=0,
        cache_write=0,
        total_tokens=total,
        cost=UsageCost(input=0, output=0, cache_read=0, cache_write=0, total=0),
    )


def _tool(name: str, delay: float) -> AgentTool[EmptyArgs, AgentToolResult]:
    async def execute(_call_id, _params, _abort, _update):
        await asyncio.sleep(delay)
        return AgentToolResult(content=(TextContent(text=f"{name}-out"),), details=None)

    return AgentTool(
        name=name,
        label=name,
        description=f"regression tool {name}",
        parameter_type=EmptyArgs,
        execute=execute,
    )


def _extension_root(tmp_path: Path) -> Path:
    root = tmp_path / "insert-extension"
    root.mkdir()
    (root / "pi-extension.json").write_text(INSERT_EXTENSION_MANIFEST, encoding="utf-8")
    (root / "main.py").write_text(INSERT_EXTENSION_MAIN, encoding="utf-8")
    return root


def _session_entries(tmp_path: Path) -> list[dict[str, object]]:
    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1
    return [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines()]


def test_extension_message_during_tool_execution_does_not_split_the_pair(
    tmp_path: Path,
) -> None:
    provider = FakeProvider(
        [
            fake_assistant_message(
                ToolCall(id="t1", name="wait_tool", arguments={}), stop_reason="toolUse"
            ),
            fake_assistant_message("done"),
        ]
    )

    async def scenario() -> None:
        manager = SessionManager.create(
            cwd=tmp_path,
            session_dir=tmp_path,
            session_id="regression00000000000000000000000bb",
            timestamp="2026-09-01T00:00:00.000Z",
        )
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=ModelRuntime(provider=provider, model=fake_model()),
                session_manager=manager,
                service_overrides=ServiceOverrides(
                    resource_roots=(
                        ResourceRoot(
                            kind="extension", source="explicit", path=_extension_root(tmp_path)
                        ),
                    )
                ),
                tools=(_tool("wait_tool", 0.05),),
            )
        )
        try:
            await created.session.prompt("go")
        finally:
            await created.close()

    asyncio.run(scenario())
    records = _session_entries(tmp_path)
    roles = [record.get("message", {}).get("role") or record.get("type") for record in records[1:]]
    # The extension message must land after the tool result, never between the
    # tool call and its result.
    tool_call_index = roles.index("assistant")  # first assistant carries the tool call
    assert str(records[1 + tool_call_index]["message"]["content"]).find("toolCall") >= 0
    assert roles[tool_call_index + 1] == "toolResult"
    custom_index = next(index for index, role in enumerate(roles) if role == "custom_message")
    assert custom_index > tool_call_index + 1


def test_auto_compaction_lands_before_the_next_provider_request(tmp_path: Path) -> None:
    huge = fake_assistant_message("tool turn", stop_reason="toolUse")
    provider = FakeProvider(
        [
            replace(
                fake_assistant_message(
                    ToolCall(id="t1", name="wait_tool", arguments={}), stop_reason="toolUse"
                ),
                usage=_usage(128_000),
            ),
            replace(huge, stop_reason="stop", usage=_usage(128_000)),
            fake_assistant_message("## Goal\n- compacted checkpoint"),
            fake_assistant_message("after compaction"),
        ]
    )

    async def scenario() -> tuple[object, list[str]]:
        manager = SessionManager.create(
            cwd=tmp_path,
            session_dir=tmp_path,
            session_id="regression00000000000000000000000cc",
            timestamp="2026-09-01T00:00:00.000Z",
        )
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=ModelRuntime(provider=provider, model=fake_model()),
                session_manager=manager,
                tools=(_tool("wait_tool", 0.0),),
                compaction_reserve_tokens=100,
                compaction_keep_recent_tokens=1,
                compaction_token_count=lambda _entry: 500,
            )
        )
        try:
            await created.session.prompt("inspect")
            await created.session.prompt("continue")
            second_request = provider.calls[-1][1].messages
            texts = []
            for message in second_request:
                content = getattr(message, "content", None)
                summary = getattr(message, "summary", None)
                if isinstance(summary, str):
                    texts.append(summary)
                if isinstance(content, str):
                    texts.append(content)
                for block in content or ():
                    if isinstance(block, TextContent):
                        texts.append(block.text)
            return created.session.messages, texts
        finally:
            await created.close()

    _messages, texts = asyncio.run(scenario())
    assert any("compacted checkpoint" in text for text in texts)
    # The cut keeps only the newest live assistant message; the executed tool
    # result from the previous turn must already be summarized away.
    assert not any("wait_tool-out" in text for text in texts)


def test_parallel_tool_results_persist_individually_in_model_order(tmp_path: Path) -> None:
    provider = FakeProvider(
        [
            fake_assistant_message(
                (
                    ToolCall(id="t1", name="slow_tool", arguments={}),
                    ToolCall(id="t2", name="quick_tool", arguments={}),
                ),
                stop_reason="toolUse",
            ),
            fake_assistant_message("both done"),
        ]
    )

    async def scenario() -> None:
        manager = SessionManager.create(
            cwd=tmp_path,
            session_dir=tmp_path,
            session_id="regression00000000000000000000000dd",
            timestamp="2026-09-01T00:00:00.000Z",
        )
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=ModelRuntime(provider=provider, model=fake_model()),
                session_manager=manager,
                tools=(_tool("slow_tool", 0.05), _tool("quick_tool", 0.0)),
            )
        )
        try:
            await created.session.prompt("run both")
        finally:
            await created.close()

    asyncio.run(scenario())
    records = _session_entries(tmp_path)
    results = [
        record["message"]
        for record in records
        if record.get("message", {}).get("role") == "toolResult"
    ]
    assert len(results) == 2, "each parallel tool result must be its own entry"
    assert [result["toolCallId"] for result in results] == ["t1", "t2"]
