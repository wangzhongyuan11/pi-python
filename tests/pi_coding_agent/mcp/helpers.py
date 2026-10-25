"""Shared offline MCP server fixtures for Phase 18 tests."""

from __future__ import annotations

import sys
from pathlib import Path

from pi_coding_agent.mcp.contracts import ServerSpec

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


def write_echo_server(directory: Path) -> ServerSpec:
    """Materialize a JSONL stdio echo MCP server and return its spec."""

    server_script = directory / "echo_server.py"
    server_script.write_text(chr(10).join(_ECHO_SERVER_LINES), encoding="utf-8")
    return ServerSpec(
        kind="stdio", name="echo", command=[sys.executable, str(server_script)]
    )
