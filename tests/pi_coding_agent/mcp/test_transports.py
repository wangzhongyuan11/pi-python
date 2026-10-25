"""P18-T01: MCP transport abstraction (red tests first).

A transport connects to one MCP server, performs the JSON-RPC initialize
handshake, exchanges framed JSON-RPC messages, and reports structured
lifecycle errors (connect/cancel/timeout).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from pi_coding_agent.mcp.contracts import McpTransportError, ServerSpec
from pi_coding_agent.mcp.transports import create_stdio_transport


def test_server_spec_parses_stdio_command() -> None:
    spec = ServerSpec(kind="stdio", name="files", command=["npx", "@mcp/server-files"])

    assert spec.kind == "stdio"
    assert spec.name == "files"
    assert spec.command == ["npx", "@mcp/server-files"]


def test_server_spec_requires_a_command_for_stdio() -> None:
    with pytest.raises(ValueError, match="command"):
        ServerSpec(kind="stdio", name="broken", command=[])


def test_stdio_transport_initializes_and_answers_requests(tmp_path: Path) -> None:
    server_script = tmp_path / "server.py"
    server_script.write_text(
        "\n".join(
            [
                "import json, sys",
                "for line in sys.stdin:",
                "    req = json.loads(line)",
                "    if req.get('method') == 'initialize':",
                "        resp = {'jsonrpc': '2.0', 'id': req['id'], 'result': "
                "{'protocolVersion': '2025-06-18', 'capabilities': {'tools': {}}, "
                "'serverInfo': {'name': 'files', 'version': '1.0'}}}",
                "    elif req.get('method') == 'tools/list':",
                "        resp = {'jsonrpc': '2.0', 'id': req['id'], 'result': {'tools': ["
                "{'name': 'read_file', 'description': 'Read a file', "
                "'inputSchema': {'type': 'object', 'properties': {}}}]}}",
                "    else:",
                "        resp = {'jsonrpc': '2.0', 'id': req.get('id'), "
                "'error': {'code': -32601, 'message': 'not found'}}",
                "    sys.stdout.write(json.dumps(resp) + '\\n')",
                "    sys.stdout.flush()",
            ]
        ),
        encoding="utf-8",
    )
    spec = ServerSpec(kind="stdio", name="files", command=[sys_executable(), str(server_script)])
    transport = create_stdio_transport(spec)

    async def scenario() -> None:
        started = await asyncio.wait_for(transport.start(), 30)
        assert started.server_info is not None
        assert started.server_info["name"] == "files"
        reply = await asyncio.wait_for(transport.request("tools/list", {}), 30)
        assert reply["tools"][0]["name"] == "read_file"
        await transport.close()

    asyncio.run(scenario())


_HANDSHAKE_ONLY_SERVER = (
    "import json, sys, time\n"
    "for line in sys.stdin:\n"
    "    req = json.loads(line)\n"
    "    if req.get('method') == 'initialize':\n"
    "        resp = {'jsonrpc': '2.0', 'id': req['id'], 'result': "
    "{'protocolVersion': '2025-06-18', 'capabilities': {}, "
    "'serverInfo': {'name': 'silent', 'version': '1'}}}\n"
    "        sys.stdout.write(json.dumps(resp) + chr(10)); sys.stdout.flush()\n"
    "        break\n"
    "time.sleep(120)\n"
)


def test_stdio_transport_request_times_out_deterministically(tmp_path: Path) -> None:
    # A server that never answers: the request must fail with a transport
    # error carrying the timeout code.
    server_script = tmp_path / "handshake-only.py"
    server_script.write_text(_HANDSHAKE_ONLY_SERVER, encoding="utf-8")
    spec = ServerSpec(kind="stdio", name="silent", command=[sys_executable(), str(server_script)])
    transport = create_stdio_transport(spec)

    async def scenario() -> None:
        await asyncio.wait_for(transport.start(), 30)
        with pytest.raises(McpTransportError, match="timed out"):
            await transport.request("tools/list", {}, timeout=1)
        await transport.close()

    asyncio.run(scenario())


def test_close_terminates_a_silent_server(tmp_path: Path) -> None:
    server_script = tmp_path / "handshake-only2.py"
    server_script.write_text(_HANDSHAKE_ONLY_SERVER, encoding="utf-8")
    spec = ServerSpec(kind="stdio", name="silent2", command=[sys_executable(), str(server_script)])
    transport = create_stdio_transport(spec)

    async def scenario() -> None:
        await asyncio.wait_for(transport.start(), 30)
        await transport.close()
        assert transport._process is not None
        assert transport._process.returncode is not None

    asyncio.run(scenario())


def sys_executable() -> str:
    import sys

    return sys.executable
