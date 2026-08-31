from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

from pi_coding_agent.cli.packages import run_package_command
from pi_coding_agent.config.settings import SettingsManager
from pi_coding_agent.packages.manager import DefaultPackageManager


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _fixture(source: Path) -> None:
    _write(
        source / "package.json",
        json.dumps({"name": "lifecycle", "pi": {"skills": ["skills"]}}),
    )
    _write(source / "skills" / "demo.md", "# Demo")


def _manager(agent_dir: Path, project: Path) -> DefaultPackageManager:
    return DefaultPackageManager(
        settings=SettingsManager.load(agent_dir=agent_dir, cwd=project, project_trusted=True)
    )


def test_enable_disable_and_remove_are_persistent_and_immediate(tmp_path: Path) -> None:
    agent_dir = tmp_path / "agent"
    project = tmp_path / "project"
    source = tmp_path / "source" / "lifecycle"
    _fixture(source)
    manager = _manager(agent_dir, project)
    manager.install_local(source)

    assert manager.resource_roots()
    assert manager.set_enabled(str(source.resolve()), False) is True
    assert manager.resource_roots() == ()
    disabled = _manager(agent_dir, project).list_configured_packages()[0]
    assert disabled.enabled is False
    assert disabled.installed_path == agent_dir / "packages" / "lifecycle"

    restarted = _manager(agent_dir, project)
    assert restarted.set_enabled(str(source.resolve()), True) is True
    assert restarted.resource_roots()
    assert restarted.remove_installed(str(source.resolve())) is True
    assert restarted.resource_roots() == ()
    assert restarted.list_configured_packages() == ()
    assert not (agent_dir / "packages" / "lifecycle").exists()


def test_package_cli_lists_configures_and_removes_installed_sources(
    tmp_path: Path,
) -> None:
    agent_dir = tmp_path / "agent"
    project = tmp_path / "project"
    source = tmp_path / "source" / "lifecycle"
    _fixture(source)
    _manager(agent_dir, project).install_local(source)
    project.mkdir()
    environ = {"PI_PYTHON_AGENT_DIR": str(agent_dir)}

    output = io.StringIO()
    errors = io.StringIO()
    assert (
        run_package_command(
            argparse.Namespace(command="list"),
            stdout=output,
            stderr=errors,
            cwd=project,
            environ=environ,
        )
        == 0
    )
    assert str(source.resolve()) in output.getvalue()

    assert (
        run_package_command(
            argparse.Namespace(
                command="config",
                name=str(source.resolve()),
                state="disabled",
                local=False,
                approve=False,
            ),
            stdout=output,
            stderr=errors,
            cwd=project,
            environ=environ,
        )
        == 0
    )
    assert _manager(agent_dir, project).resource_roots() == ()

    assert (
        run_package_command(
            argparse.Namespace(
                command="remove",
                source=str(source.resolve()),
                local=False,
                approve=False,
            ),
            stdout=output,
            stderr=errors,
            cwd=project,
            environ=environ,
        )
        == 0
    )
    assert _manager(agent_dir, project).list_configured_packages() == ()
