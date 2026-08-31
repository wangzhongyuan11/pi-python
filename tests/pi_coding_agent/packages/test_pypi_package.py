from __future__ import annotations

import json
from pathlib import Path

from pi_coding_agent.config.settings import SettingsManager
from pi_coding_agent.packages.manager import DefaultPackageManager


class FakePyPi:
    def __init__(self) -> None:
        self.latest = "1.0.0"

    def install(self, requirement: str, target: Path) -> None:
        version = requirement.partition("==")[2] or self.latest
        (target / "skills").mkdir(parents=True)
        (target / "package.json").write_text(
            json.dumps({"name": "pypi-package", "pi": {"skills": ["skills"]}}),
            encoding="utf-8",
        )
        (target / "skills" / "version.md").write_text(version, encoding="utf-8")


def _manager(tmp_path: Path, index: FakePyPi) -> DefaultPackageManager:
    return DefaultPackageManager(
        settings=SettingsManager.load(
            agent_dir=tmp_path / "agent",
            cwd=tmp_path / "project",
            project_trusted=True,
        ),
        pypi_installer=index.install,
    )


def test_pypi_install_discovers_resources_and_respects_pinned_versions(
    tmp_path: Path,
) -> None:
    index = FakePyPi()
    manager = _manager(tmp_path, index)
    installed = tmp_path / "agent" / "packages" / "pypi-package/skills/version.md"

    manager.install_pypi("demo-package")
    assert installed.read_text(encoding="utf-8") == "1.0.0"
    assert {root.kind for root in manager.resource_roots()} == {"skill"}

    index.latest = "2.0.0"
    manager.update_pypi("demo-package")
    assert installed.read_text(encoding="utf-8") == "2.0.0"

    manager.remove_installed("demo-package")
    manager.install_pypi("demo-package==1.0.0")
    index.latest = "3.0.0"
    manager.update_pypi("demo-package==1.0.0")
    assert installed.read_text(encoding="utf-8") == "1.0.0"
