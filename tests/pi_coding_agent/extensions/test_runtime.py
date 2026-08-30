from __future__ import annotations

import json
from pathlib import Path

from pi_coding_agent.extensions.metadata import read_manifest
from pi_coding_agent.extensions.runtime import DefaultExtensionRuntime
from pi_coding_agent.resources.default_loader import DefaultResourceLoader


def _extension(root: Path, marker: Path) -> Path:
    directory = root / "example"
    directory.mkdir(parents=True)
    (directory / "pi-extension.json").write_text(
        json.dumps({"name": "example", "version": "1.0.0", "entry": "main.py"}),
        encoding="utf-8",
    )
    (directory / "main.py").write_text(
        "def activate(api):\n"
        "    api.define_command('hello', lambda value: value.upper())\n"
        f"    return lambda: open({str(marker)!r}, 'w', encoding='utf-8').write('closed')\n",
        encoding="utf-8",
    )
    return directory


def test_runtime_enumerates_without_loading_until_identity_is_trusted(tmp_path: Path) -> None:
    marker = tmp_path / "closed.txt"
    extensions = tmp_path / "extensions"
    directory = _extension(extensions, marker)
    loader = DefaultResourceLoader(
        agent_dir=tmp_path / "agent",
        extension_roots=(extensions,),
    )
    runtime = DefaultExtensionRuntime(cwd=tmp_path / "project", resources=loader)

    import asyncio

    discovered = asyncio.run(runtime.start())
    assert [item.name for item in discovered] == ["example"]
    assert runtime.registry.registrations() == ()

    asyncio.run(runtime.close())
    runtime.grant_trust(read_manifest(directory))
    asyncio.run(runtime.start())

    command = runtime.registry.lookup("command", "hello")
    assert command is not None
    assert command.payload("hi") == "HI"  # type: ignore[operator]
    asyncio.run(runtime.close())
    assert marker.read_text(encoding="utf-8") == "closed"
