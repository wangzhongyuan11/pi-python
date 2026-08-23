"""The unique composition root shared by CLI and SDK entry points."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .services import ProductServices, ServiceOverrides, create_product_services


@dataclass(frozen=True, slots=True, kw_only=True)
class BootstrapConfig:
    cwd: Path
    service_overrides: ServiceOverrides = field(default_factory=ServiceOverrides)


class ProductBootstrap:
    __slots__ = ("_config", "_services")

    def __init__(self, config: BootstrapConfig) -> None:
        self._config = config
        self._services = create_product_services(config.cwd, config.service_overrides)

    @property
    def config(self) -> BootstrapConfig:
        return self._config

    @property
    def services(self) -> ProductServices:
        return self._services


def bootstrap(config: BootstrapConfig) -> ProductBootstrap:
    return ProductBootstrap(config)


__all__ = ["BootstrapConfig", "ProductBootstrap", "bootstrap"]
