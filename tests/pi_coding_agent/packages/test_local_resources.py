from __future__ import annotations

import json
from pathlib import Path

import pytest

from pi_coding_agent.config.settings import SettingsManager
from pi_coding_agent.packages.manager import DefaultPackageManager
from pi_coding_agent.packages.manifest import PackageManifestError
from pi_coding_agent.resources.default_loader import DefaultResourceLoader


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _package(source: Path, *, skill_text: str = "# Golden skill") -> None:
    _write(
        source / "package.json",
        json.dumps(
            {
                "name": "golden-package",
                "pi": {
                    "skills": ["resources/skills"],
                    "prompts": ["resources/prompts"],
                    "themes": ["resources/themes"],
                },
            }
        ),
    )
    _write(source / "resources" / "skills" / "golden" / "SKILL.md", skill_text)
    _write(source / "resources" / "prompts" / "review.md", "Review carefully")
    _write(source / "resources" / "themes" / "golden.json", '{"name":"golden"}')


def _manager(agent_dir: Path, project: Path) -> DefaultPackageManager:
    return DefaultPackageManager(
        settings=SettingsManager.load(
            agent_dir=agent_dir,
            cwd=project,
            project_trusted=True,
        )
    )


def test_local_package_install_survives_restart_and_enters_resource_discovery(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source" / "golden-package"
    agent_dir = tmp_path / "agent"
    project = tmp_path / "project"
    _package(source)
    manager = _manager(agent_dir, project)

    roots = manager.install_local(source)

    installed = agent_dir / "packages" / "golden-package"
    assert installed.is_dir()
    assert all(root.source == "package" for root in roots)
    assert {root.kind for root in roots} == {"skill", "prompt", "theme"}
    assert manager.list_configured_packages()[0].source == str(source.resolve())

    restarted = _manager(agent_dir, project)
    loader = DefaultResourceLoader(
        agent_dir=agent_dir,
        resource_roots=restarted.resource_roots(),
    )
    descriptors = loader.discover(project)

    assert {(item.kind, item.name, item.source) for item in descriptors} >= {
        ("skill", "SKILL", "package"),
        ("prompt", "review", "package"),
        ("theme", "golden", "package"),
    }
    skill = next(item for item in descriptors if item.kind == "skill")
    assert skill.path is not None
    assert skill.path.relative_to(installed).as_posix() == ("resources/skills/golden/SKILL.md")


def test_failed_local_update_preserves_the_previous_installed_package(tmp_path: Path) -> None:
    source = tmp_path / "source" / "golden-package"
    agent_dir = tmp_path / "agent"
    project = tmp_path / "project"
    _package(source, skill_text="# Version one")
    manager = _manager(agent_dir, project)
    manager.install_local(source)
    installed_skill = agent_dir / "packages" / "golden-package/resources/skills/golden/SKILL.md"

    _write(
        source / "package.json",
        json.dumps(
            {
                "name": "golden-package",
                "pi": {"skills": ["../outside"]},
            }
        ),
    )

    with pytest.raises(PackageManifestError, match="outside package root"):
        manager.install_local(source)

    assert installed_skill.read_text(encoding="utf-8") == "# Version one"
    assert not tuple((agent_dir / "packages").glob(".*.staging"))
    assert not tuple((agent_dir / "packages").glob(".*.backup"))
