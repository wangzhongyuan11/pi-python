"""P15.5-T04: node handlers join the shared hook fan-out and action routing."""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import pytest

from pi_coding_agent.extensions.events import (
    ExtensionAgentEndEvent,
    ExtensionTurnStartEvent,
    ToolCallEvent,
)
from pi_coding_agent.extensions.hooks import HookRunner
from pi_coding_agent.extensions.registry import CapabilityRegistry
from pi_coding_agent.node_host.event_bridge import (
    NodeActionBridge,
    NodeEventBridge,
    NodeHostStaleError,
    combine_handlers,
)
from pi_coding_agent.node_host.process import NodeHostProcess
from pi_coding_agent.node_host.registry_bridge import RegistryBridge

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not available")

EVENTS_EXTENSION = """\
import { appendFileSync } from "node:fs";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const LOG = __LOG__;

function log(entry) {
  appendFileSync(LOG, JSON.stringify(entry) + "\\n");
}

export default function (pi: ExtensionAPI) {
  pi.on("turn_start", (event) => {
    log(["turn_start", event.turnIndex]);
  });
  pi.on("agent_end", () => {
    log(["agent_end"]);
  });
  pi.on("tool_call", (event) => {
    if (event.toolName === "guarded") {
      return { block: true, reason: "blocked-by-node" };
    }
    return undefined;
  });
  pi.registerCommand("node-notify", {
    description: "Sends a message through the bridge",
    handler: async (args) => {
      await pi.sendMessage("node-note", `note:${args}`);
      return `noted:${args}`;
    },
  });
}
"""


class RecordingActions:
    """Records action calls; structurally matches the action protocol."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def send_message(self, custom_type: str, content: str, **kwargs: object) -> str:
        self.calls.append(("send_message", (custom_type, content, kwargs)))
        return "entry-1"

    def send_user_message(self, content: str, *, deliver_as: str = "follow_up") -> object:
        self.calls.append(("send_user_message", (content, deliver_as)))
        return "queued"

    def append_entry(self, custom_type: str, data: object = None) -> str:
        self.calls.append(("append_entry", (custom_type, data)))
        return "entry-2"

    def set_session_name(self, name: str) -> str:
        self.calls.append(("set_session_name", name))
        return name

    def get_session_name(self) -> str | None:
        return None

    def set_label(self, entry_id: str, label: str | None) -> str:
        self.calls.append(("set_label", (entry_id, label)))
        return entry_id

    async def exec(self, command: str, args: tuple[str, ...], **kwargs: object) -> object:
        self.calls.append(("exec", (command, args)))
        return None

    def get_active_tools(self) -> tuple[str, ...]:
        return ("read",)

    def set_active_tools(self, names: tuple[str, ...] | list[str]) -> None:
        self.calls.append(("set_active_tools", tuple(names)))

    def get_commands(self) -> tuple[object, ...]:
        return ()

    def set_model(self, model: str) -> bool:
        self.calls.append(("set_model", model))
        return True

    def get_thinking_level(self) -> str:
        return "off"

    def set_thinking_level(self, level: str) -> None:
        self.calls.append(("set_thinking_level", level))


async def _boot(
    tmp_path: Path, log: Path
) -> tuple[
    NodeHostProcess,
    HookRunner,
    NodeEventBridge,
    NodeActionBridge,
    RecordingActions,
    CapabilityRegistry,
]:
    directory = tmp_path / "events-ext"
    directory.mkdir()
    (directory / "main.ts").write_text(
        EVENTS_EXTENSION.replace("__LOG__", json.dumps(str(log))), encoding="utf-8"
    )
    process = NodeHostProcess(extensions=[directory / "main.ts"], cwd=tmp_path)
    hooks = HookRunner()
    event_bridge = NodeEventBridge(host_caller=process.request)
    actions = RecordingActions()
    action_bridge = NodeActionBridge(actions_provider=lambda: actions)
    registry = CapabilityRegistry()
    registry_bridge = RegistryBridge(registry, source="node-host:test", host_caller=process.request)
    process.set_request_handler(combine_handlers(registry_bridge, action_bridge))
    await process.start()
    event_bridge.register_forwarders(
        hooks,
        {"turn_start": "turn_start", "agent_end": "agent_end", "tool_call": "tool_call"},
    )
    return process, hooks, event_bridge, action_bridge, actions, registry


def test_lifecycle_events_forward_in_order(tmp_path: Path) -> None:
    log = tmp_path / "events.jsonl"

    async def scenario() -> list[object]:
        process, hooks, _eb, _ab, _actions, _registry = await _boot(tmp_path, log)
        try:
            await hooks.emit("turn_start", ExtensionTurnStartEvent(turn_index=2, timestamp=1))
            await hooks.emit("agent_end", ExtensionAgentEndEvent(messages=()))
            return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        finally:
            await process.close()

    lines = asyncio.run(scenario())
    assert lines[0] == ["turn_start", 2]
    assert lines[1] == ["agent_end"]


def test_control_hook_blocks_a_tool_call(tmp_path: Path) -> None:
    log = tmp_path / "events.jsonl"

    async def scenario() -> list[tuple[bool, object]]:
        process, hooks, _eb, _ab, _actions, _registry = await _boot(tmp_path, log)
        try:
            event = ToolCallEvent(tool_call_id="c1", tool_name="guarded", input={"path": "x"})
            outcomes = await hooks.emit("tool_call", event)
            return [(outcome.ok, outcome.value) for outcome in outcomes]
        finally:
            await process.close()

    outcomes = asyncio.run(scenario())
    assert outcomes == [(True, {"block": True, "reason": "blocked-by-node"})]


def test_session_actions_route_to_the_bound_actions(tmp_path: Path) -> None:
    log = tmp_path / "events.jsonl"

    async def scenario() -> tuple[object, list[tuple[str, object]]]:
        process, _hooks, _event_bridge, _action_bridge, actions, registry = await _boot(
            tmp_path, log
        )
        try:
            commands = [
                item.payload for item in registry.registrations("command") if callable(item.payload)
            ]
            result = await commands[0]("hello", None)
            # The action request is processed concurrently with the command
            # response; let the bridge task run before asserting.
            for _ in range(200):
                if actions.calls:
                    break
                await asyncio.sleep(0.01)
            return result, actions.calls
        finally:
            await process.close()

    result, calls = asyncio.run(scenario())
    assert result == "noted:hello"
    assert calls and calls[0][0] == "send_message"


def test_stale_generation_stops_forwarding_and_rejects_requests(tmp_path: Path) -> None:
    log = tmp_path / "events.jsonl"

    async def scenario() -> int:
        process, hooks, event_bridge, action_bridge, _actions, _registry = await _boot(
            tmp_path, log
        )
        try:
            await hooks.emit("turn_start", ExtensionTurnStartEvent(turn_index=0, timestamp=1))
            assert log.exists()
            before = len(log.read_text(encoding="utf-8").splitlines())
            event_bridge.invalidate()
            action_bridge.invalidate()
            await hooks.emit("turn_start", ExtensionTurnStartEvent(turn_index=1, timestamp=2))
            after = len(log.read_text(encoding="utf-8").splitlines())
            return after - before
        finally:
            await process.close()

    assert asyncio.run(scenario()) == 0


def test_unbound_actions_reject_with_stale_semantics() -> None:
    bridge = NodeActionBridge(actions_provider=lambda: None)

    async def scenario() -> object:
        return await bridge.handle_request("send_message", {})

    async def invalidated() -> object:
        bridge.invalidate()
        return await bridge.handle_request("send_message", {})

    with pytest.raises(RuntimeError, match="no session is bound"):
        asyncio.run(scenario())
    with pytest.raises(NodeHostStaleError):
        asyncio.run(invalidated())
