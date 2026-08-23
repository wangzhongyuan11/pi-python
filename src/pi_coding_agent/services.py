"""Stable service bundle owned by the product composition root."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pi_tui import UI, NoopUI

from .ports import (
    DefaultSessionImporter,
    ExtensionRuntime,
    InMemorySettings,
    NoopExtensionRuntime,
    NoopResourceLoader,
    NoopSessionExporter,
    ResourceLoader,
    SessionExporter,
    SessionImporter,
    Settings,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ServiceOverrides:
    settings: Settings | None = None
    resources: ResourceLoader | None = None
    extensions: ExtensionRuntime | None = None
    exporter: SessionExporter | None = None
    importer: SessionImporter | None = None
    ui: UI | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ProductServices:
    cwd: Path
    settings: Settings
    resources: ResourceLoader
    extensions: ExtensionRuntime
    exporter: SessionExporter
    importer: SessionImporter
    ui: UI


def create_product_services(
    cwd: Path,
    overrides: ServiceOverrides | None = None,
) -> ProductServices:
    selected = ServiceOverrides() if overrides is None else overrides
    return ProductServices(
        cwd=cwd.resolve(),
        settings=selected.settings if selected.settings is not None else InMemorySettings(),
        resources=(selected.resources if selected.resources is not None else NoopResourceLoader()),
        extensions=(
            selected.extensions if selected.extensions is not None else NoopExtensionRuntime()
        ),
        exporter=(selected.exporter if selected.exporter is not None else NoopSessionExporter()),
        importer=(selected.importer if selected.importer is not None else DefaultSessionImporter()),
        ui=selected.ui if selected.ui is not None else NoopUI(),
    )


__all__ = ["ProductServices", "ServiceOverrides", "create_product_services"]
