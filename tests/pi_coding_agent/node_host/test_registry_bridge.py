"""P15.5-T03: node registrations become real Python registry entries."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest

from pi_agent import AgentTool
from pi_coding_agent.extensions.registry import CapabilityRegistry, FlagState
from pi_coding_agent.node_host.process import NodeHostProcess
from pi_coding_agent.node_host.registry_bridge import RegistryBridge

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not available")

FULL_EXTENSION = """\
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function (pi: ExtensionAPI) {
  pi.registerTool({
    name: "node_echo",
    label: "Node echo",
    description: "Echoes a value through the node host",
    parameters: {
      type: "object",
      properties: { text: { type: "string" } },
      required: ["text"],
    },
    execute: async (_id, params) => ({
      content: [{ type: "text", text: `node:${params.text}` }],
      details: { via: "node" },
    }),
  });
  pi.registerCommand("node-hello", {
    description: "Greets from node",
    handler: async (args) => `node-hello:${args}`,
  });
  pi.registerFlag("--node-flag", { type: "boolean", default: false });
  pi.registerShortcut("ctrl+shift+9", {
    description: "Node shortcut",
    handler: async () => undefined,
  });
}
"""


def _extension(tmp_path: Path, body: str) -> Path:
    directory = tmp_path / "full"
    directory.mkdir()
    (directory / "main.ts").write_text(body, encoding="utf-8")
    return directory / "main.ts"


async def _boot(tmp_path: Path) -> tuple[NodeHostProcess, CapabilityRegistry]:
    entry = _extension(tmp_path, FULL_EXTENSION)
    registry = CapabilityRegistry()
    process = NodeHostProcess(extensions=[entry], cwd=tmp_path)
    bridge = RegistryBridge(registry, source="node-host:test", host_caller=process.request)
    process.set_request_handler(bridge.handle_request)
    await process.start()
    return process, registry


def test_registrations_land_in_the_python_registry_and_proxy_back(
    tmp_path: Path,
) -> None:
    async def scenario() -> tuple[object, object, object, object]:
        process, registry = await _boot(tmp_path)
        try:
            tools = [
                item.payload
                for item in registry.registrations("tool")
                if isinstance(item.payload, AgentTool)
            ]
            assert [tool.name for tool in tools] == ["node_echo"]
            params = tools[0].parameter_type(text="hi")
            result = await tools[0].execute("call-1", params, None, None)

            commands = [
                item.payload for item in registry.registrations("command") if callable(item.payload)
            ]
            command_result = await commands[0]("world", None)

            flags = [
                item.payload
                for item in registry.registrations("flag")
                if isinstance(item.payload, FlagState)
            ]
            shortcuts = [
                item.payload
                for item in registry.registrations("shortcut")
                if callable(item.payload)
            ]
            return result, command_result, flags, (shortcuts, len(shortcuts))
        finally:
            await process.close()

    result, command_result, flags, shortcuts = asyncio.run(scenario())
    texts = [block.text for block in result.content]
    assert texts == ["node:hi"]
    assert result.details == {"via": "node"}
    assert command_result == "node-hello:world"
    assert len(flags) == 1
    assert flags[0].value is False
    assert shortcuts[1] == 1


def test_state_updates_are_accepted_by_the_host(tmp_path: Path) -> None:
    async def scenario() -> object:
        process, registry = await _boot(tmp_path)
        try:
            return await process.request(
                "update_state", {"state": {"flags": {"--node-flag": True}}}
            )
        finally:
            await process.close()

    assert asyncio.run(scenario()) == {"ok": True}


def test_registry_conflicts_fail_the_bridge_request(tmp_path: Path) -> None:
    from pi_coding_agent.extensions.registry import RegistryConflictError

    async def scenario() -> object:
        process, registry = await _boot(tmp_path)
        try:
            bridge = RegistryBridge(registry, source="node-host:dupe", host_caller=process.request)
            return await bridge.handle_request(
                "register_tool",
                {
                    "definition": {
                        "name": "node_echo",
                        "label": "dupe",
                        "description": "dupe",
                        "parameters": {"type": "object", "properties": {}},
                    }
                },
            )
        finally:
            await process.close()

    with pytest.raises(RegistryConflictError, match="already registered"):
        asyncio.run(scenario())
