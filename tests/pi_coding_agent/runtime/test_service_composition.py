from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from pi_coding_agent.extensions.runtime import DefaultExtensionRuntime
from pi_coding_agent.ports import ResourceRoot
from pi_coding_agent.resources.default_loader import DefaultResourceLoader
from pi_coding_agent.services import ServiceOverrides, create_product_services


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _write_extension(root: Path, name: str) -> Path:
    extension = root / name
    _write_json(
        extension / "pi-extension.json",
        {"name": name, "version": "0.1.0", "entry": "main.py"},
    )
    (extension / "main.py").write_text("def activate(api):\n    return None\n", encoding="utf-8")
    return extension.resolve()


def test_settings_package_and_explicit_roots_share_one_loader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent_dir = tmp_path / "agent"
    project = tmp_path / "project"
    configured_skill = agent_dir / "configured.md"
    configured_skill.parent.mkdir(parents=True)
    configured_skill.write_text("# configured", encoding="utf-8")
    _write_json(agent_dir / "settings.json", {"skills": ["configured.md"]})
    package_root = tmp_path / "package" / "skills"
    package_root.mkdir(parents=True)
    package_skill = package_root / "packaged.md"
    package_skill.write_text("# packaged", encoding="utf-8")
    explicit_extensions = tmp_path / "explicit-extensions"
    extension = _write_extension(explicit_extensions, "fixture")
    monkeypatch.setenv("PI_PYTHON_AGENT_DIR", str(agent_dir))

    services = create_product_services(
        project,
        ServiceOverrides(
            resource_roots=(
                ResourceRoot(kind="skill", path=package_root, source="package"),
                ResourceRoot(kind="extension", path=extension, source="explicit"),
            )
        ),
    )

    assert isinstance(services.resources, DefaultResourceLoader)
    assert isinstance(services.extensions, DefaultExtensionRuntime)
    assert services.resources.resolved_roots == (
        ResourceRoot(kind="skill", path=package_root.resolve(), source="package"),
        ResourceRoot(kind="extension", path=extension, source="explicit"),
        ResourceRoot(kind="skill", path=configured_skill.resolve(), source="explicit"),
    )

    discovered = services.resources.discover(project)
    extension_descriptors = asyncio.run(services.extensions.start())

    assert {(item.name, item.source) for item in discovered} >= {
        ("configured", "explicit"),
        ("packaged", "package"),
    }
    assert [(item.path, item.source) for item in extension_descriptors] == [(extension, "explicit")]


def test_custom_resource_loader_requires_a_matching_extension_runtime(tmp_path: Path) -> None:
    from pi_coding_agent.ports import NoopResourceLoader

    with pytest.raises(ValueError, match="custom resource loader requires"):
        create_product_services(
            tmp_path,
            ServiceOverrides(resources=NoopResourceLoader()),
        )
