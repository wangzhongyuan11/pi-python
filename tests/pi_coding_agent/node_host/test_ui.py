"""P15.5-T05: node UI dialogs route to the product UI; renderers unsupported."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest

from pi_coding_agent.extensions.hooks import HookRunner
from pi_coding_agent.extensions.registry import CapabilityRegistry
from pi_coding_agent.node_host.event_bridge import (
    NodeActionBridge,
    NodeEventBridge,
    combine_handlers,
)
from pi_coding_agent.node_host.process import NodeHostProcess
from pi_coding_agent.node_host.registry_bridge import RegistryBridge
from pi_coding_agent.node_host.ui_bridge import NodeUiBridge

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not available")

UI_EXTENSION = """\
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function (pi: ExtensionAPI) {
  let rendererUnsupported = "";
  try {
    pi.registerMessageRenderer("node-custom", () => "x");
  } catch (error) {
    rendererUnsupported = (error as Error).message;
  }
  pi.registerCommand("node-ask", {
    description: "Asks through the product UI",
    handler: async (args) => {
      const answer = await pi.ui.input("Your name", "type here");
      const confirmed = await pi.ui.confirm("Proceed?", "really?");
      const choice = await pi.ui.select("Pick one", ["alpha", "beta"]);
      pi.ui.notify(`notify:${args}`);
      pi.ui.setStatus(`status:${args}`);
      const renderer = rendererUnsupported ? "unsupported" : "accepted";
      return `answer:${answer}|confirmed:${confirmed}|choice:${choice}|renderer:${renderer}`;
    },
  });
}
"""


class RecordingUi:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def input(self, prompt: str, *, default: str = "") -> str | None:
        self.calls.append(("input", (prompt, default)))
        return "Ada"

    async def confirm(self, prompt: str) -> bool | None:
        self.calls.append(("confirm", prompt))
        return True

    async def select(self, title: str, options: tuple[str, ...]) -> str | None:
        self.calls.append(("select", (title, options)))
        return "beta"

    def notify(self, text: str) -> None:
        self.calls.append(("notify", text))

    def set_status(self, key: str, value: str | None) -> None:
        self.calls.append(("set_status", (key, value)))


async def _boot(
    tmp_path: Path, ui_provider: object
) -> tuple[NodeHostProcess, CapabilityRegistry, RecordingUi]:
    directory = tmp_path / "ui-ext"
    directory.mkdir()
    (directory / "main.ts").write_text(UI_EXTENSION, encoding="utf-8")
    process = NodeHostProcess(extensions=[directory / "main.ts"], cwd=tmp_path)
    hooks = HookRunner()
    event_bridge = NodeEventBridge(host_caller=process.request)
    ui = ui_provider  # type: ignore[assignment]
    ui_bridge = NodeUiBridge(ui_provider=lambda: ui)  # type: ignore[arg-type, return-value]
    action_bridge = NodeActionBridge(actions_provider=lambda: None)
    registry = CapabilityRegistry()
    registry_bridge = RegistryBridge(registry, source="node-host:test", host_caller=process.request)
    process.set_request_handler(combine_handlers(registry_bridge, ui_bridge, action_bridge))
    await process.start()
    event_bridge.register_forwarders(hooks, {})
    return process, registry, ui  # type: ignore[return-value]


def test_ui_dialogs_route_to_the_product_ui(tmp_path: Path) -> None:
    async def scenario() -> tuple[object, RecordingUi]:
        process, registry, ui = await _boot(tmp_path, RecordingUi())
        try:
            commands = [
                item.payload for item in registry.registrations("command") if callable(item.payload)
            ]
            result = await asyncio.wait_for(commands[0]("hi", None), 20)
            return result, ui
        finally:
            await process.close()

    result, ui = asyncio.run(scenario())
    assert result == "answer:Ada|confirmed:true|choice:beta|renderer:unsupported"
    assert ("input", ("Your name", "type here")) in ui.calls
    assert ("confirm", "Proceed?") in ui.calls
    assert ("select", ("Pick one", ("alpha", "beta"))) in ui.calls
    assert ("notify", "notify:hi") in ui.calls
    assert ("set_status", ("extension", "status:hi")) in ui.calls


def test_headless_ui_degrades_instead_of_failing(tmp_path: Path) -> None:
    async def scenario() -> object:
        process, registry, _ui = await _boot(tmp_path, None)
        try:
            commands = [
                item.payload for item in registry.registrations("command") if callable(item.payload)
            ]
            return await asyncio.wait_for(commands[0]("hi", None), 20)
        finally:
            await process.close()

    result = asyncio.run(scenario())
    assert result == "answer:null|confirmed:false|choice:null|renderer:unsupported"
