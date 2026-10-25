"""Offline JSONL stdio MCP echo server used by Phase 18 product tests.

Set ECHO_CRASH_AFTER_CALLS=1 to exit after answering that many tools/call
requests, simulating a server crash mid-session.
"""

import json
import os
import sys

tools = [
    {
        "name": "echo_tool",
        "description": "Echo the input text",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    }
]

crash_budget = int(os.environ.get("ECHO_CRASH_AFTER_CALLS", "0"))
calls_answered = 0

for line in sys.stdin:
    request = json.loads(line)
    method = request.get("method", "")
    if method == "initialize":
        result = {
            "protocolVersion": "2025-06-18",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "echo", "version": "1.0"},
        }
    elif method == "tools/list":
        result = {"tools": tools}
    elif method == "tools/call":
        text = (request.get("params", {}).get("arguments", {}) or {}).get("text", "")
        result = {"content": [{"type": "text", "text": "echo:" + text}], "isError": False}
        calls_answered += 1
    else:
        result = {}
    if "id" in request:
        reply = {"jsonrpc": "2.0", "id": request["id"], "result": result}
        sys.stdout.write(json.dumps(reply) + "\n")
        sys.stdout.flush()
    if crash_budget and calls_answered >= crash_budget:
        sys.exit(0)
