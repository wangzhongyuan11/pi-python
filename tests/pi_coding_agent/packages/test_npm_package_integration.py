from __future__ import annotations

import gzip
import io
import json
import shutil
import tarfile
from pathlib import Path

from pi_coding_agent.config.settings import SettingsManager
from pi_coding_agent.packages.manager import DefaultPackageManager


def _tarball(path: Path) -> Path:
    members = {
        "package/package.json": json.dumps({"name": "npm-data", "version": "1.2.0", "scripts": {}}),
        "package/skills/npm.md": "# npm skill",
        "package/prompts/npm.md": "npm prompt",
        "package/themes/npm.json": "{}",
    }
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as archive:
        for name, text in members.items():
            payload = text.encode()
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    path.write_bytes(gzip.compress(raw.getvalue()))
    return path


def test_npm_data_package_enters_resource_roots_without_loading_code(tmp_path: Path) -> None:
    fixture = _tarball(tmp_path / "fixture.tgz")

    def pack(_spec: str, cache: Path) -> Path:
        target = cache / "npm-data-1.2.0.tgz"
        shutil.copy2(fixture, target)
        return target

    manager = DefaultPackageManager(
        settings=SettingsManager.load(
            agent_dir=tmp_path / "agent",
            cwd=tmp_path / "project",
            project_trusted=True,
        ),
        npm_pack_runner=pack,
    )

    roots = manager.install_npm_data("npm:npm-data@1.2.0")

    assert {root.kind for root in roots} == {"skill", "prompt", "theme"}
    assert manager.list_configured_packages()[0].source == "npm:npm-data@1.2.0"
    installed = tmp_path / "agent" / "packages" / "npm-data"
    assert (installed / "skills/npm.md").is_file()
    assert not tuple(installed.rglob("*.js"))
