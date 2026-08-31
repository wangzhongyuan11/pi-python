from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from pi_coding_agent.config.settings import SettingsManager
from pi_coding_agent.packages.manager import DefaultPackageManager
from pi_coding_agent.resources.default_loader import DefaultResourceLoader

_GOLDEN_PACKAGE = Path(__file__).parents[2] / "fixtures" / "golden_package"


def _entrypoint() -> Path:
    name = "pi-python.exe" if os.name == "nt" else "pi-python"
    return Path(sys.executable).with_name(name)


def _run_cli(
    *arguments: str,
    cwd: Path,
    agent_dir: Path,
) -> subprocess.CompletedProcess[str]:
    environ = dict(os.environ)
    environ["PI_PYTHON_AGENT_DIR"] = str(agent_dir)
    return subprocess.run(
        [_entrypoint(), *arguments],
        cwd=cwd,
        env=environ,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )


def _manager(agent_dir: Path, cwd: Path) -> DefaultPackageManager:
    return DefaultPackageManager(settings=SettingsManager.load(agent_dir=agent_dir, cwd=cwd))


def test_package_cli_survives_restart_and_completes_local_lifecycle(
    tmp_path: Path,
) -> None:
    agent_dir = tmp_path / "agent"
    project = tmp_path / "project"
    source = tmp_path / "source" / "golden-package"
    project.mkdir()
    shutil.copytree(_GOLDEN_PACKAGE, source)
    source_text = str(source.resolve())

    installed = _run_cli("install", source_text, cwd=project, agent_dir=agent_dir)
    assert installed.returncode == 0, installed.stderr
    assert installed.stdout == f"Installed {source_text}\n"

    listed = _run_cli("list", cwd=project, agent_dir=agent_dir)
    assert listed.returncode == 0, listed.stderr
    assert listed.stdout == f"user: {source_text} (enabled)\n"

    manager = _manager(agent_dir, project)
    roots = manager.resource_roots()
    assert {root.kind for root in roots} == {"skill", "prompt", "theme"}
    resources = DefaultResourceLoader(resource_roots=roots, agent_dir=agent_dir).discover(project)
    assert {(item.kind, item.name, item.source) for item in resources} == {
        ("skill", "golden-skill", "package"),
        ("prompt", "golden-prompt", "package"),
        ("theme", "golden-theme", "package"),
    }

    disabled = _run_cli(
        "config",
        source_text,
        "disabled",
        cwd=project,
        agent_dir=agent_dir,
    )
    assert disabled.returncode == 0, disabled.stderr
    assert _manager(agent_dir, project).resource_roots() == ()
    restarted_list = _run_cli("list", cwd=project, agent_dir=agent_dir)
    assert restarted_list.stdout == f"user: {source_text} (disabled)\n"

    enabled = _run_cli(
        "config",
        source_text,
        "enabled",
        cwd=project,
        agent_dir=agent_dir,
    )
    assert enabled.returncode == 0, enabled.stderr
    (source / "prompts" / "golden-prompt.md").write_text(
        "---\ndescription: Golden prompt v2\n---\nupdated body\n",
        encoding="utf-8",
    )
    updated = _run_cli(
        "update",
        "--offline",
        source_text,
        cwd=project,
        agent_dir=agent_dir,
    )
    assert updated.returncode == 0, updated.stderr
    assert updated.stdout == f"Updated {source_text}\n"
    installed_prompt = agent_dir / "packages" / "golden-package" / "prompts" / "golden-prompt.md"
    assert "Golden prompt v2" in installed_prompt.read_text(encoding="utf-8")

    removed = _run_cli("remove", source_text, cwd=project, agent_dir=agent_dir)
    assert removed.returncode == 0, removed.stderr
    assert removed.stdout == f"Removed {source_text}\n"
    final_list = _run_cli("list", cwd=project, agent_dir=agent_dir)
    assert final_list.returncode == 0, final_list.stderr
    assert final_list.stdout == "No packages installed.\n"
    assert _manager(agent_dir, project).resource_roots() == ()
    assert not (agent_dir / "packages" / "golden-package").exists()
