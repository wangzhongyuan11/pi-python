from __future__ import annotations

import asyncio
import json
from pathlib import Path

from pi_coding_agent.extensions.runtime import DefaultExtensionRuntime
from pi_coding_agent.resources.default_loader import DefaultResourceLoader


def _extension(root: Path, name: str) -> Path:
    directory = root / name
    directory.mkdir(parents=True)
    (directory / "pi-extension.json").write_text(
        json.dumps({"name": name, "version": "1.0.0", "entry": "main.py"}),
        encoding="utf-8",
    )
    (directory / "main.py").write_text(
        f"def activate(api):\n    api.define_command({name!r}, lambda value: value or {name!r})\n",
        encoding="utf-8",
    )
    return directory


def test_explicit_and_global_extensions_activate_without_ephemeral_grants(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    agent_dir = tmp_path / "agent"
    explicit_root = tmp_path / "explicit"
    project.mkdir()
    _extension(explicit_root, "explicit-command")
    _extension(agent_dir / "extensions", "global-command")
    resources = DefaultResourceLoader(
        agent_dir=agent_dir,
        extension_roots=(explicit_root,),
    )
    runtime = DefaultExtensionRuntime(cwd=project, resources=resources)

    asyncio.run(runtime.start())

    assert runtime.registry.lookup("command", "explicit-command") is not None
    assert runtime.registry.lookup("command", "global-command") is not None


def test_project_extension_activation_follows_only_resolved_project_trust(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    agent_dir = tmp_path / "agent"
    project.mkdir()
    _extension(project / ".pi-python" / "extensions", "project-command")
    resources = DefaultResourceLoader(agent_dir=agent_dir)
    runtime = DefaultExtensionRuntime(cwd=project, resources=resources)

    asyncio.run(runtime.start())
    assert runtime.registry.lookup("command", "project-command") is None

    asyncio.run(runtime.close())
    resources.set_project_trusted(project, True)
    asyncio.run(runtime.start())
    assert runtime.registry.lookup("command", "project-command") is not None
