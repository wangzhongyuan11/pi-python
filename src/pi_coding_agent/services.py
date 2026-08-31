"""Stable service bundle owned by the product composition root."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pi_tui import UI, NoopUI

from .config.settings import SettingsManager
from .extensions.runtime import DefaultExtensionRuntime
from .ports import (
    DefaultSessionImporter,
    ExtensionRuntime,
    NoopSessionExporter,
    ResourceKind,
    ResourceLoader,
    ResourceRoot,
    SessionExporter,
    SessionImporter,
    Settings,
)
from .resources.default_loader import DefaultResourceLoader
from .resources.trust import FileProjectTrustStore


@dataclass(frozen=True, slots=True, kw_only=True)
class ServiceOverrides:
    settings: Settings | None = None
    resources: ResourceLoader | None = None
    extensions: ExtensionRuntime | None = None
    exporter: SessionExporter | None = None
    importer: SessionImporter | None = None
    ui: UI | None = None
    resource_roots: tuple[ResourceRoot, ...] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class ProductServices:
    cwd: Path
    settings: Settings
    resources: ResourceLoader
    extensions: ExtensionRuntime
    exporter: SessionExporter
    importer: SessionImporter
    ui: UI
    _static_resource_roots: tuple[ResourceRoot, ...] = ()

    def reload_project_trust(self, trusted: bool) -> None:
        """Reload settings and resources after resolving project trust."""
        if not isinstance(self.settings, SettingsManager):
            raise RuntimeError("project trust reload requires the default SettingsManager")
        self.settings.reload(project_trusted=trusted)
        if isinstance(self.resources, DefaultResourceLoader):
            self.resources.set_resource_roots(
                (*self._static_resource_roots, *_settings_resource_roots(self.settings))
            )
            self.resources.set_project_trusted(self.cwd, trusted)
            self.resources.load(cwd=self.cwd, agent_dir=self.resources.agent_dir)


def create_product_services(
    cwd: Path,
    overrides: ServiceOverrides | None = None,
) -> ProductServices:
    selected = ServiceOverrides() if overrides is None else overrides
    resolved_cwd = cwd.resolve()
    settings = selected.settings
    if settings is None:
        settings = SettingsManager.load(
            agent_dir=_agent_dir(),
            cwd=resolved_cwd,
            project_trusted=False,
        )
    settings_roots = _settings_resource_roots(settings)
    default_resources = DefaultResourceLoader(
        trust_store=FileProjectTrustStore(_agent_dir() / "trust.json"),
        agent_dir=_agent_dir(),
        resource_roots=(*selected.resource_roots, *settings_roots),
    )
    default_resources.set_project_trusted(resolved_cwd, False)
    resources = selected.resources if selected.resources is not None else default_resources
    if selected.extensions is None:
        if not isinstance(resources, DefaultResourceLoader):
            raise ValueError("custom resource loader requires a matching extension runtime")
        extensions: ExtensionRuntime = DefaultExtensionRuntime(cwd=cwd, resources=resources)
    else:
        extensions = selected.extensions
    return ProductServices(
        cwd=resolved_cwd,
        settings=settings,
        resources=resources,
        extensions=extensions,
        exporter=(selected.exporter if selected.exporter is not None else NoopSessionExporter()),
        importer=(selected.importer if selected.importer is not None else DefaultSessionImporter()),
        ui=selected.ui if selected.ui is not None else NoopUI(),
        _static_resource_roots=selected.resource_roots,
    )


def _settings_resource_roots(settings: Settings) -> tuple[ResourceRoot, ...]:
    if not isinstance(settings, SettingsManager):
        return ()
    singular: dict[str, ResourceKind] = {
        "extensions": "extension",
        "skills": "skill",
        "prompts": "prompt",
        "themes": "theme",
    }
    return tuple(
        ResourceRoot(kind=kind, path=path, source="explicit")
        for plural, kind in singular.items()
        for path in settings.resource_paths(plural)
    )


def _agent_dir() -> Path:
    import os

    configured = os.environ.get("PI_PYTHON_AGENT_DIR")
    return (Path(configured) if configured else Path.home() / ".pi-python" / "agent").resolve()


__all__ = ["ProductServices", "ServiceOverrides", "create_product_services"]
