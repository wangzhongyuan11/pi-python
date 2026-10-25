"""P18-T04: MCP tools load on demand — search plus incremental activation."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from pi_ai import FakeProvider, ToolCall, fake_assistant_message, fake_model
from pi_coding_agent.mcp.contracts import ServerSpec
from pi_coding_agent.mcp.host import McpHost
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.sdk import CreateAgentSessionOptions, create_agent_session

_ECHO_SERVER_LINES = [
    "import json, sys",
    "tools = [{'name': 'echo_tool', 'description': 'Echo the input', "
    "'inputSchema': {'type': 'object', 'properties': {'text': {'type': 'string'}}, "
    "'required': ['text']}}]",
    "for line in sys.stdin:",
    "    req = json.loads(line)",
    "    method = req.get('method', '')",
    "    if method == 'initialize':",
    "        result = {'protocolVersion': '2025-06-18', 'capabilities': {'tools': {}}, "
    "'serverInfo': {'name': 'echo', 'version': '1.0'}}",
    "    elif method == 'tools/list':",
    "        result = {'tools': tools}",
    "    elif method == 'tools/call':",
    "        text = (req.get('params', {}).get('arguments', {}) or {}).get('text', '')",
    "        result = {'content': [{'type': 'text', 'text': 'echo:' + text}], 'isError': False}",
    "    else:",
    "        result = {}",
    "    if 'id' in req:",
    "        reply = {'jsonrpc': '2.0', 'id': req['id'], 'result': result}",
    "        sys.stdout.write(json.dumps(reply) + chr(10))",
    "        sys.stdout.flush()",
]

_ECHO_SERVER = chr(10).join(_ECHO_SERVER_LINES)


def _provider(*responses: object) -> ModelRuntime:
    provider = FakeProvider(list(responses))
    return ModelRuntime(provider=provider, model=provider.models[0])


def _spec(tmp_path: Path) -> ServerSpec:
    server_script = tmp_path / "echo_server.py"
    server_script.write_text(_ECHO_SERVER, encoding="utf-8")
    return ServerSpec(kind="stdio", name="echo", command=[sys.executable, str(server_script)])


def test_search_tool_and_incremental_activation_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PI_PYTHON_AGENT_DIR", str(tmp_path / "agent"))

    async def scenario() -> tuple[bool, bool, str]:
        host = McpHost()
        await host.start([_spec(tmp_path)])
        provider = _provider(
            fake_assistant_message(
                ToolCall(id="s1", name="mcp_search", arguments={"query": "echo"}),
                stop_reason="toolUse",
            ),
            fake_assistant_message(
                ToolCall(id="s2", name="echo_tool", arguments={"text": "activated"}),
                stop_reason="toolUse",
            ),
            fake_assistant_message("activated and called"),
        )
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=provider,
                mcp_host=host,
            )
        )
        try:
            names = tuple(tool.name for tool in created.session.agent.state.tools)
            await created.session.prompt("find the echo tool and call it")
            names_after = tuple(tool.name for tool in created.session.agent.state.tools)
            texts = [
                block.text
                for message in created.session.messages
                for block in getattr(message, "content", ()) or ()
                if getattr(block, "type", "") == "text"
            ]
            return "echo_tool" in names, "echo_tool" in names_after, "\n".join(texts)
        finally:
            await created.close()
            await host.close()

    echo_before, echo_after, transcript = asyncio.run(scenario())
    assert echo_before is False
    assert echo_after is True
    assert "echo:activated" in transcript


def test_mcp_search_lists_tools_without_activating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PI_PYTHON_AGENT_DIR", str(tmp_path / "agent"))

    async def scenario() -> bool:
        host = McpHost()
        await host.start([_spec(tmp_path)])
        provider = _provider(fake_assistant_message("done"))
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=provider,
                mcp_host=host,
            )
        )
        try:
            await created.session.prompt("search for the echo tool")
            names_after = tuple(tool.name for tool in created.session.agent.state.tools)
            return "echo_tool" in names_after
        finally:
            await created.close()
            await host.close()

    activated = asyncio.run(scenario())
    assert activated is False
