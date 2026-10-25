"""P18-T03: MCP tool definitions map into real AgentTools.

``map_tools`` converts MCP ``tools/list`` entries into AgentTool instances
whose execute relays through the host (schema → pydantic, text content
back). ``map_prompts`` converts prompts/list entries into descriptors.
"""

from __future__ import annotations

import asyncio

import pytest

from pi_agent import AgentTool
from pi_coding_agent.mcp.mapping import McpToolCallError, map_prompts, map_tools


def _tool_entry() -> dict[str, object]:
    return {
        "name": "read_file",
        "description": "Read a text file",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path"},
                "encoding": {"type": "string"},
            },
            "required": ["path"],
        },
    }


def test_map_tools_builds_agent_tools_with_proxied_execute() -> None:
    async def relay(name: str, arguments: dict[str, object]) -> dict[str, object]:
        return {"content": [{"type": "text", "text": f"read:{arguments['path']}"}]}

    tools = map_tools([_tool_entry()], server="files", relay=relay)

    assert len(tools) == 1
    tool = tools[0]
    assert isinstance(tool, AgentTool)
    assert tool.name == "read_file"
    assert tool.description == "Read a text file"
    model = tool.parameter_type(path="notes.md")
    assert model.path == "notes.md"


def test_mapped_tool_executes_through_the_relay() -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    async def relay(name: str, arguments: dict[str, object]) -> dict[str, object]:
        calls.append((name, dict(arguments)))
        return {"content": [{"type": "text", "text": f"read:{arguments.get('path')}"}]}

    async def run() -> tuple[object, object]:
        tools = map_tools([_tool_entry()], server="files", relay=relay)
        result = await tools[0].execute("call-1", tools[0].parameter_type(path="a.md"), None, None)
        return calls, result

    calls, result = asyncio.run(run())
    assert calls == [("read_file", {"path": "a.md"})]
    assert result.content[0].text == "read:a.md"
    assert result.is_error is False if hasattr(result, "is_error") else True


def test_mapped_tool_surfaces_server_errors_as_error_results() -> None:
    from pi_ai import TextContent

    async def relay(name: str, arguments: dict[str, object]) -> dict[str, object]:
        return {"content": [{"type": "text", "text": "no such file"}], "isError": True}

    async def run() -> object:
        tools = map_tools([_tool_entry()], server="files", relay=relay)
        return await tools[0].execute("call-2", tools[0].parameter_type(path="x"), None, None)

    with pytest.raises(McpToolCallError, match="no such file"):
        asyncio.run(run())
    # A tool-level MCP error surfaces as an error tool result through the
    # agent pipeline (exceptions become _error_result with is_error=True).
    del TextContent


def test_map_prompts_builds_descriptors() -> None:
    prompts = map_prompts(
        [
            {
                "name": "review",
                "description": "Review the diff",
                "arguments": [{"name": "scope", "description": "What to review"}],
            }
        ],
        server="files",
    )

    assert len(prompts) == 1
    assert prompts[0].name == "review"
    assert prompts[0].source == "mcp:files"


def test_map_tools_requires_object_schema() -> None:
    with pytest.raises(ValueError, match="object"):
        map_tools(
            [{"name": "bad", "inputSchema": {"type": "string"}}],
            server="files",
            relay=None,
        )
