"""P15.5-T02: managed Node process loads upstream-style TypeScript extensions."""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import pytest

from pi_coding_agent.node_host.process import (
    DependencyInstaller,
    NodeHostError,
    NodeHostProcess,
    host_entry,
)

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not available")

OFFICIAL_STYLE_TS = """\
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function (pi: ExtensionAPI) {
  let started = false;
  pi.on("agent_start", () => {
    started = true;
  });
  pi.getFlag("--official-mode");
}
"""


def _write_extension(root: Path, name: str, body: str) -> Path:
    directory = root / name
    directory.mkdir(parents=True)
    (directory / "pi-extension.json").write_text(
        json.dumps({"name": name, "version": "1.0.0", "entry": "main.ts"}), encoding="utf-8"
    )
    (directory / "main.ts").write_text(body, encoding="utf-8")
    return directory / "main.ts"


async def _boot(extensions: list[Path], tmp_path: Path, **kwargs: object) -> NodeHostProcess:
    process = NodeHostProcess(
        extensions=extensions,
        cwd=tmp_path,
        **kwargs,  # type: ignore[arg-type]
    )
    ack = await process.start()
    assert ack.protocol == 1
    assert "register_tool" in ack.capabilities
    return process


def test_official_style_typescript_extension_loads_through_the_managed_process(
    tmp_path: Path,
) -> None:
    entry = _write_extension(tmp_path, "official-style", OFFICIAL_STYLE_TS)

    async def scenario() -> tuple[dict[str, object], object]:
        process = await _boot([entry], tmp_path)
        try:
            assert len(process.extensions) == 1
            loaded = process.extensions[0]
            assert not loaded.get("error")
            return loaded, await process.request("ping")
        finally:
            await process.close()

    loaded, ping = asyncio.run(scenario())
    assert not loaded.get("error")
    assert ping == {"pong": True}


def test_broken_and_non_factory_extensions_report_errors_without_killing_the_host(
    tmp_path: Path,
) -> None:
    syntax_error = _write_extension(tmp_path, "broken", "def activate(:\n")
    not_a_factory = _write_extension(tmp_path, "not-factory", "export default 42;\n")
    healthy = _write_extension(tmp_path, "healthy", OFFICIAL_STYLE_TS)

    async def scenario() -> tuple[object, object]:
        process = await _boot([syntax_error, not_a_factory, healthy], tmp_path)
        try:
            return process.extensions, await process.request("ping")
        finally:
            await process.close()

    extensions, ping = asyncio.run(scenario())
    errors = [str(item["error"]) for item in extensions if item.get("error")]
    assert len(errors) == 2
    assert ping == {"pong": True}


def test_host_rejects_unknown_commands_with_typed_errors(tmp_path: Path) -> None:
    entry = _write_extension(tmp_path, "plain", OFFICIAL_STYLE_TS)

    async def scenario() -> object:
        process = await _boot([entry], tmp_path)
        try:
            return await process.request("make_coffee")
        finally:
            await process.close()

    with pytest.raises(NodeHostError, match="unknown command"):
        asyncio.run(scenario())


def test_dependency_installer_runs_once_per_module_root_with_dependencies(
    tmp_path: Path,
) -> None:
    entry = _write_extension(tmp_path, "with-deps", OFFICIAL_STYLE_TS)
    (entry.parent / "package.json").write_text(
        json.dumps({"name": "with-deps", "dependencies": {"left-pad": "1.3.0"}}),
        encoding="utf-8",
    )
    plain = _write_extension(tmp_path, "no-deps", OFFICIAL_STYLE_TS)
    installed: list[Path] = []

    class RecordingInstaller(DependencyInstaller):
        def install(self, module_root: Path) -> None:
            installed.append(module_root)

    async def scenario() -> None:
        process = await _boot([entry, plain], tmp_path, installer=RecordingInstaller())
        try:
            assert len(process.extensions) == 2
        finally:
            await process.close()

    asyncio.run(scenario())
    assert installed == [entry.parent]


def test_host_entry_env_override_fails_typed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PI_PYTHON_NODE_HOST_DIR", str(tmp_path / "missing"))
    with pytest.raises(NodeHostError, match="host entry not found"):
        host_entry(tmp_path)
