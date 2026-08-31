from __future__ import annotations

import json
from pathlib import Path

import pytest

from pi_coding_agent.config.settings import SettingsManager
from pi_coding_agent.packages.manager import DefaultPackageManager
from pi_coding_agent.ports import ConfiguredPackage, PackageManager


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _load_manager(agent_dir: Path, project: Path) -> DefaultPackageManager:
    settings = SettingsManager.load(
        agent_dir=agent_dir,
        cwd=project,
        project_trusted=True,
    )
    manager = DefaultPackageManager(settings=settings)
    assert isinstance(manager, PackageManager)
    return manager


def test_package_sources_persist_by_scope_and_survive_restart(tmp_path: Path) -> None:
    agent_dir = tmp_path / "agent"
    project = tmp_path / "project"
    _write_json(
        agent_dir / "settings.json",
        {"theme": "dark", "futureGlobal": {"keep": True}},
    )
    _write_json(
        project / ".pi-python" / "settings.json",
        {"quietStartup": True, "futureProject": "keep"},
    )
    manager = _load_manager(agent_dir, project)

    assert manager.add_source("example-package") is True
    assert manager.add_source("example-package") is False
    assert manager.add_source("../project-package", scope="project") is True

    restarted = _load_manager(agent_dir, project)
    assert restarted.list_configured_packages() == (
        ConfiguredPackage(source="example-package", scope="user", filtered=False),
        ConfiguredPackage(source="../project-package", scope="project", filtered=False),
    )
    assert json.loads((agent_dir / "settings.json").read_text(encoding="utf-8")) == {
        "theme": "dark",
        "futureGlobal": {"keep": True},
        "packages": ["example-package"],
    }
    assert json.loads((project / ".pi-python" / "settings.json").read_text(encoding="utf-8")) == {
        "quietStartup": True,
        "futureProject": "keep",
        "packages": ["../project-package"],
    }

    assert restarted.remove_source("example-package") is True
    assert restarted.remove_source("example-package") is False
    assert restarted.remove_source("../project-package", scope="project") is True
    assert _load_manager(agent_dir, project).list_configured_packages() == ()


def test_filtered_sources_are_listed_without_losing_their_configuration(
    tmp_path: Path,
) -> None:
    agent_dir = tmp_path / "agent"
    project = tmp_path / "project"
    configured = {
        "source": "filtered-package",
        "autoload": False,
        "skills": ["skills/only-this.md"],
    }
    _write_json(agent_dir / "settings.json", {"packages": [configured]})

    manager = _load_manager(agent_dir, project)

    assert manager.list_configured_packages() == (
        ConfiguredPackage(source="filtered-package", scope="user", filtered=True, enabled=False),
    )
    assert manager.add_source("filtered-package") is False
    assert manager.remove_source("filtered-package") is True


def test_project_package_writes_require_project_trust(tmp_path: Path) -> None:
    settings = SettingsManager.load(
        agent_dir=tmp_path / "agent",
        cwd=tmp_path / "project",
        project_trusted=False,
    )
    manager = DefaultPackageManager(settings=settings)

    with pytest.raises(PermissionError, match="project trust"):
        manager.add_source("../project-package", scope="project")
