from __future__ import annotations

import shutil
import tarfile
from pathlib import Path

from pi_coding_agent.config.models import PackageSource
from pi_coding_agent.config.settings import SettingsManager
from pi_coding_agent.packages import DefaultPackageManager, inspect_package
from pi_coding_agent.resources.default_loader import DefaultResourceLoader

FIXTURE = Path(__file__).parents[2] / "fixtures" / "upstream_package"


def _settings(agent_dir: Path, project: Path) -> SettingsManager:
    return SettingsManager.load(agent_dir=agent_dir, cwd=project, project_trusted=True)


def _tarball_from_fixture(path: Path) -> Path:
    with tarfile.open(path, "w:gz") as archive:
        for source in sorted(FIXTURE.rglob("*")):
            if source.is_file():
                archive.add(source, arcname=f"package/{source.relative_to(FIXTURE).as_posix()}")
    return path


def test_upstream_package_survives_restart_with_portable_and_dual_runtime_resources(
    tmp_path: Path,
) -> None:
    agent_dir = tmp_path / "agent"
    project = tmp_path / "project"
    settings = _settings(agent_dir, project)
    manager = DefaultPackageManager(settings=settings)

    manager.install_local(FIXTURE)
    source = str(FIXTURE.resolve())
    settings.set_package_sources(
        (
            PackageSource(
                source=source,
                prompts=("prompts/*.md", "-prompts/legacy.md"),
            ),
        ),
        scope="user",
    )

    restarted = DefaultPackageManager(settings=_settings(agent_dir, project))
    roots = restarted.resource_roots()
    loader = DefaultResourceLoader(agent_dir=agent_dir, resource_roots=roots)
    result = loader.load(cwd=project, agent_dir=agent_dir)
    installed = agent_dir / "packages" / "upstream-compatible-package"
    report = inspect_package(installed)

    assert (installed / "extensions/official.ts").is_file()
    assert {item.name for item in result.extensions} == {"upstream-python-proof"}
    assert {(item.kind, item.name) for item in result.descriptors} >= {
        ("skill", "SKILL"),
        ("prompt", "review"),
        ("theme", "upstream"),
    }
    assert ("prompt", "legacy") not in {(item.kind, item.name) for item in result.descriptors}
    assert report.overall == "bridged"
    assert any(item.path == "extensions/official.ts" for item in report.capabilities)


def test_offline_npm_fixture_uses_the_same_restart_and_discovery_path(tmp_path: Path) -> None:
    fixture = _tarball_from_fixture(tmp_path / "upstream-package.tgz")
    agent_dir = tmp_path / "agent"
    project = tmp_path / "project"

    def pack(_spec: str, cache: Path) -> Path:
        target = cache / fixture.name
        shutil.copy2(fixture, target)
        return target

    manager = DefaultPackageManager(settings=_settings(agent_dir, project), npm_pack_runner=pack)
    manager.install_npm_data("npm:upstream-compatible-package@1.0.0")

    restarted = DefaultPackageManager(settings=_settings(agent_dir, project))
    loader = DefaultResourceLoader(
        agent_dir=agent_dir,
        resource_roots=restarted.resource_roots(),
    )
    result = loader.load(cwd=project, agent_dir=agent_dir)
    installed = agent_dir / "packages" / "upstream-compatible-package"

    assert {(item.kind, item.name) for item in result.descriptors} >= {
        ("skill", "SKILL"),
        ("prompt", "review"),
        ("theme", "upstream"),
    }
    assert {item.name for item in result.extensions} == {"upstream-python-proof"}
    assert inspect_package(installed).overall == "bridged"
