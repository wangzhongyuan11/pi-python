"""P15.5-T06: supervised node host lifecycle inside the product composition."""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import pytest

from pi_ai import FakeProvider, ToolCall, fake_assistant_message
from pi_coding_agent.extensions.runtime import DefaultExtensionRuntime
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.node_host.process import NodeHostError
from pi_coding_agent.node_host.runtime import NodeHostRuntime
from pi_coding_agent.resources.default_loader import DefaultResourceLoader
from pi_coding_agent.sdk import CreateAgentSessionOptions, create_agent_session

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not available")

NODE_ECHO_TS = """\
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function (pi: ExtensionAPI) {
  pi.registerTool({
    name: "node_echo",
    label: "Node echo",
    description: "Echoes through the node host",
    parameters: {
      type: "object",
      properties: { text: { type: "string" } },
      required: ["text"],
    },
    execute: async (_id, params) => ({
      content: [{ type: "text", text: `node:${params.text}` }],
      details: null,
    }),
  });
}
"""


def _extension(tmp_path: Path) -> Path:
    directory = tmp_path / "node-ext"
    directory.mkdir()
    (directory / "main.ts").write_text(NODE_ECHO_TS, encoding="utf-8")
    return directory / "main.ts"


def _runtime(tmp_path: Path) -> DefaultExtensionRuntime:
    return DefaultExtensionRuntime(
        cwd=tmp_path,
        resources=DefaultResourceLoader(agent_dir=tmp_path / "agent"),
        ui=None,
    )


def test_reload_boots_a_fresh_generation_and_replaces_registrations(
    tmp_path: Path,
) -> None:
    entry = _extension(tmp_path)

    async def scenario() -> tuple[int, int, int, int]:
        runtime = _runtime(tmp_path)
        host = NodeHostRuntime(extensions_runtime=runtime, cwd=tmp_path)
        await host.start([entry])
        old_process = host._process
        first_generation = host.generation
        first_tools = len(runtime.registry.registrations("tool"))
        await host.reload([entry])
        new_tools = len(runtime.registry.registrations("tool"))
        new_generation = host.generation
        assert host._process is not old_process
        await host.close()
        return first_generation, first_tools, new_generation, new_tools

    first_generation, first_tools, new_generation, new_tools = asyncio.run(scenario())
    assert (first_generation, first_tools) == (1, 1)
    assert (new_generation, new_tools) == (2, 1)


def test_crash_is_recorded_and_does_not_leak(tmp_path: Path) -> None:
    entry = _extension(tmp_path)

    async def scenario() -> tuple[bool, int]:
        runtime = _runtime(tmp_path)
        host = NodeHostRuntime(extensions_runtime=runtime, cwd=tmp_path)
        await host.start([entry])
        assert host._process is not None and host._process._process is not None
        host._process._process.kill()
        for _ in range(200):
            if host.failed:
                break
            await asyncio.sleep(0.01)
        failed = host.failed
        diagnostics = len(host.diagnostics)
        await host.close()
        return failed, diagnostics

    failed, diagnostics = asyncio.run(scenario())
    assert failed is True
    assert diagnostics >= 1


def test_close_removes_registrations_and_stops_the_process(tmp_path: Path) -> None:
    entry = _extension(tmp_path)

    async def scenario() -> tuple[int, int]:
        runtime = _runtime(tmp_path)
        host = NodeHostRuntime(extensions_runtime=runtime, cwd=tmp_path)
        await host.start([entry])
        before = len(runtime.registry.registrations("tool"))
        await host.close()
        after = len(runtime.registry.registrations("tool"))
        return before, after

    before, after = asyncio.run(scenario())
    assert before == 1
    assert after == 0


def test_unavailable_node_host_fails_typed_and_leaves_registry_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = _extension(tmp_path)

    async def scenario() -> tuple[bool, object]:
        monkeypatch.setattr("pi_coding_agent.node_host.process.shutil.which", lambda name: None)
        runtime = _runtime(tmp_path)
        host = NodeHostRuntime(extensions_runtime=runtime, cwd=tmp_path)
        failed_typed = False
        try:
            await host.start([entry])
        except NodeHostError:
            failed_typed = True
        await host.close()
        return failed_typed, runtime.registry.registrations("tool")

    failed_typed, tools = asyncio.run(scenario())
    assert failed_typed is True
    assert list(tools) == []


def test_bridged_extension_tools_run_inside_a_real_sdk_conversation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    extension = project / ".pi-python" / "extensions" / "node-ext"
    extension.mkdir(parents=True)
    (extension / "pi-extension.json").write_text(
        json.dumps({"name": "node-ext", "version": "1.0.0", "entry": "main.ts"}),
        encoding="utf-8",
    )
    (extension / "main.ts").write_text(NODE_ECHO_TS, encoding="utf-8")
    monkeypatch.setenv("PI_PYTHON_AGENT_DIR", str(tmp_path / "agent"))
    provider = FakeProvider(
        [
            fake_assistant_message(
                ToolCall(id="n1", name="node_echo", arguments={"text": "live"}),
                stop_reason="toolUse",
            ),
            fake_assistant_message("node tool finished"),
        ]
    )

    async def scenario() -> tuple[str, ...]:
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=project,
                model_runtime=ModelRuntime(provider=provider, model=provider.models[0]),
                project_trusted=True,
            )
        )
        try:
            await created.session.prompt("use the node tool")
            names = tuple(tool.name for tool in created.session.agent.state.tools)
            from pi_ai import TextContent

            texts: list[str] = []
            for message in created.session.messages:
                content = getattr(message, "content", None)
                if isinstance(content, str):
                    texts.append(content)
                for block in content or ():
                    if isinstance(block, TextContent):
                        texts.append(block.text)
            assert "node:live" in "\n".join(texts)
            return names
        finally:
            await created.close()

    names = asyncio.run(scenario())
    assert "node_echo" in names
