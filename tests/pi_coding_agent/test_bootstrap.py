from __future__ import annotations

from pathlib import Path

import pytest

from pi_coding_agent.bootstrap import BootstrapConfig, ProductBootstrap
from pi_coding_agent.extensions.runtime import DefaultExtensionRuntime
from pi_coding_agent.ports import (
    DefaultSessionImporter,
    InMemorySettings,
    NoopExtensionRuntime,
    NoopResourceLoader,
    NoopSessionExporter,
)
from pi_coding_agent.resources.default_loader import DefaultResourceLoader
from pi_coding_agent.services import ServiceOverrides
from pi_tui import MemoryUI, NoopUI


def test_default_bootstrap_builds_one_stable_service_graph(tmp_path: Path) -> None:
    root = ProductBootstrap(BootstrapConfig(cwd=tmp_path / "project"))

    cli_services = root.services
    sdk_services = root.services

    assert cli_services is sdk_services
    assert cli_services.cwd == (tmp_path / "project").resolve()
    assert isinstance(cli_services.settings, InMemorySettings)
    assert isinstance(cli_services.resources, DefaultResourceLoader)
    assert isinstance(cli_services.extensions, DefaultExtensionRuntime)
    assert isinstance(cli_services.exporter, NoopSessionExporter)
    assert isinstance(cli_services.importer, DefaultSessionImporter)
    assert isinstance(cli_services.ui, NoopUI)


def test_bootstrap_preserves_explicit_service_identity(tmp_path: Path) -> None:
    settings = InMemorySettings({"model": "deepseek-v4-pro"})
    resources = NoopResourceLoader()
    extensions = NoopExtensionRuntime()
    exporter = NoopSessionExporter()
    importer = DefaultSessionImporter()
    ui = MemoryUI()
    overrides = ServiceOverrides(
        settings=settings,
        resources=resources,
        extensions=extensions,
        exporter=exporter,
        importer=importer,
        ui=ui,
    )

    services = ProductBootstrap(BootstrapConfig(cwd=tmp_path, service_overrides=overrides)).services

    assert services.settings is settings
    assert services.resources is resources
    assert services.extensions is extensions
    assert services.exporter is exporter
    assert services.importer is importer
    assert services.ui is ui


def test_bootstrap_instances_do_not_share_mutable_defaults(tmp_path: Path) -> None:
    first = ProductBootstrap(BootstrapConfig(cwd=tmp_path / "first"))
    second = ProductBootstrap(BootstrapConfig(cwd=tmp_path / "second"))

    first.services.settings.set("theme", "dark")

    assert first.services is not second.services
    assert first.services.settings is not second.services.settings
    assert second.services.settings.get("theme") is None


def test_default_bootstrap_loads_global_shell_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    (agent_dir / "settings.json").write_text(
        '{"shellPath":"D:\\\\Git\\\\bin\\\\bash.exe"}', encoding="utf-8"
    )
    monkeypatch.setenv("PI_PYTHON_AGENT_DIR", str(agent_dir))

    services = ProductBootstrap(BootstrapConfig(cwd=tmp_path / "project")).services

    assert services.settings.get("shellPath") == r"D:\Git\bin\bash.exe"
