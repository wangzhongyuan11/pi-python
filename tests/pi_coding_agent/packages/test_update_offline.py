from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from pi_coding_agent.config.settings import SettingsManager
from pi_coding_agent.packages.manager import DefaultPackageManager


def _local_package(path: Path, body: str) -> None:
    (path / "skills").mkdir(parents=True, exist_ok=True)
    (path / "package.json").write_text(
        json.dumps({"name": "local-update", "pi": {"skills": ["skills"]}}),
        encoding="utf-8",
    )
    (path / "skills/value.md").write_text(body, encoding="utf-8")


def test_update_scope_is_deterministic_and_offline_never_calls_remote_adapters(
    tmp_path: Path,
) -> None:
    source = tmp_path / "local"
    _local_package(source, "one")

    def no_git(_command: Sequence[str]) -> str:
        raise AssertionError("git must not run offline")

    def no_pypi(_requirement: str, _target: Path) -> None:
        raise AssertionError("pypi must not run offline")

    def no_npm(_spec: str, _cache: Path) -> Path:
        raise AssertionError("npm must not run offline")

    settings = SettingsManager.load(
        agent_dir=tmp_path / "agent",
        cwd=tmp_path / "project",
        project_trusted=True,
    )
    manager = DefaultPackageManager(
        settings=settings,
        command_runner=no_git,
        pypi_installer=no_pypi,
        npm_pack_runner=no_npm,
    )
    local_source = str(source.resolve())
    manager.install_local(source)
    manager.add_source("git+https://example.invalid/pkg.git@main")
    manager.add_source("demo-package")
    manager.add_source("npm:demo-data")
    _local_package(source, "two")

    assert manager.update(offline=True) == (local_source,)
    installed = tmp_path / "agent/packages/local-update/skills/value.md"
    assert installed.read_text(encoding="utf-8") == "two"

    with pytest.raises(ValueError, match="No matching package.*demo-packag"):
        manager.update("demo-packag")
