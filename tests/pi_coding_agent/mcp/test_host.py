"""P18-T02: McpHost owns server lifecycles (red tests).

The host boots configured servers, reconnects crashed servers, tears all of
them down on close, and exposes merged tool listings. Restart policy is
capped so a crash-looping server cannot spin forever.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from pi_coding_agent.mcp.contracts import ServerSpec
from pi_coding_agent.mcp.host import McpHost

_ECHO_SERVER = (
    "import json, sys\n"
    "initialized = False\n"
    "tools = [{'name': 'echo_tool', 'description': 'Echo the input', "
    "'inputSchema': {'type': 'object', 'properties': {'text': {'type': 'string'}}, "
    "'required': ['text']}}]\n"
    "for line in sys.stdin:\n"
    "    req = json.loads(line)\n"
    "    method = req.get('method', '')\n"
    "    if method == 'initialize':\n"
    "        initialized = True\n"
    "        result = {'protocolVersion': '2025-06-18', 'capabilities': {'tools': {}}, "
    "'serverInfo': {'name': 'echo', 'version': '1.0'}}\n"
    "    elif not initialized:\n"
    "        continue\n"
    "    elif method == 'tools/list':\n"
    "        result = {'tools': tools}\n"
    "    elif method == 'tools/call':\n"
    "        text = (req.get('params', {}).get('arguments', {}) or {}).get('text', '')\n"
    "        result = {'content': [{'type': 'text', 'text': 'echo:' + text}], 'isError': False}\n"
    "    else:\n"
    "        result = {}\n"
    "    if 'id' in req:\n"
    "        reply = {'jsonrpc': '2.0', 'id': req['id'], 'result': result}\n"
    "        sys.stdout.write(json.dumps(reply) + chr(10))\n"
    "        sys.stdout.flush()\n"
)


def _server_file(tmp_path: Path) -> Path:
    path = tmp_path / "echo_server.py"
    path.write_text(_ECHO_SERVER, encoding="utf-8")
    return path


def _echo_spec(tmp_path: Path) -> ServerSpec:
    return ServerSpec(
        kind="stdio", name="echo", command=[sys.executable, str(_server_file(tmp_path))]
    )


def test_host_boots_servers_and_lists_tools(tmp_path: Path) -> None:
    async def scenario() -> list[str]:
        host = McpHost()
        try:
            await host.start([_echo_spec(tmp_path)])
            listing = await host.list_tools()
            return [tool["name"] for tool in listing]
        finally:
            await host.close()

    assert asyncio.run(scenario()) == ["echo_tool"]


def test_host_calls_a_tool_through_the_server(tmp_path: Path) -> None:
    async def scenario() -> str:
        host = McpHost()
        try:
            await host.start([_echo_spec(tmp_path)])
            result = await host.call_tool("echo", "echo_tool", {"text": "hello"})
            content = result.get("content", [])
            return str(content[0].get("text", ""))
        finally:
            await host.close()

    assert asyncio.run(scenario()) == "echo:hello"


def test_host_restarts_a_crashed_server_within_cap(tmp_path: Path) -> None:
    async def scenario() -> tuple[bool, bool]:
        host = McpHost()
        await host.start([_echo_spec(tmp_path)])
        server = host._servers["echo"]
        assert server.transport is not None and server.transport._process is not None
        server.transport._process.kill()
        # The watchdog detects the crash and restarts automatically.
        for _ in range(100):
            if host.restart_counts.get("echo", 0) >= 1 and not host.failed_servers:
                break
            await asyncio.sleep(0.05)
        crashed = host.restart_counts.get("echo", 0) >= 1
        host._restart_cap = 1
        await host.ensure_running("echo")
        listing = await host.list_tools()
        await host.close()
        return crashed, "echo_tool" in [tool["name"] for tool in listing]

    crashed, recovered = asyncio.run(scenario())
    assert crashed is True
    assert recovered is True


def test_host_stop_closes_every_server(tmp_path: Path) -> None:
    async def scenario() -> bool:
        host = McpHost()
        await host.start([_echo_spec(tmp_path)])
        server = host._servers["echo"]
        await host.close()
        return server.transport._process.returncode is not None if server.transport else False

    assert asyncio.run(scenario()) is True


def test_host_restart_cap_stops_crash_loops(tmp_path: Path) -> None:
    async def scenario() -> int:
        host = McpHost()
        host._restart_cap = 2
        host._restart_delay = 0.05
        spec = _echo_spec(tmp_path)
        spec_command = ServerSpec(kind="stdio", name="loop", command=spec.command)
        await host.start([spec_command])
        server = host._servers["loop"]
        for _ in range(5):
            if server.transport is not None and server.transport._process is not None:
                try:
                    server.transport._process.kill()
                except ProcessLookupError:
                    pass
            await asyncio.sleep(0.2)
        count = host.restart_counts.get("loop", 0)
        await host.close()
        return count

    # count reaches cap+1: the increment happens before the cap check.
    assert asyncio.run(scenario()) <= 3
