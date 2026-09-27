"""The unique composition root shared by CLI and SDK entry points."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from pi_tui.protocols import NoopUI

from .extensions.runtime import DefaultExtensionRuntime
from .node_host.runtime import NodeHostRuntime, discover_bridged_extensions
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


async def attach_node_host(services: ProductServices, cwd: Path) -> NodeHostRuntime | None:
    """Attach a Node extension host when bridged extensions were discovered.

    Returns None when there is nothing to bridge, Node is unavailable, or the
    host fails to boot; a broken Node host never blocks the Python session.
    """

    runtime = services.extensions
    if not isinstance(runtime, DefaultExtensionRuntime):
        return None
    if shutil.which("node") is None:
        return None
    last_result = getattr(services.resources, "last_result", None)
    bridged = discover_bridged_extensions(last_result, cwd)
    if not bridged:
        return None
    node_runtime = NodeHostRuntime(
        extensions_runtime=runtime,
        cwd=cwd,
        has_ui=not isinstance(services.ui, NoopUI),
        ui_provider=lambda: services.ui,
        actions_provider=lambda: runtime.actions if runtime.actions.is_bound else None,
    )
    try:
        await node_runtime.start(bridged)
    except Exception:
        await node_runtime.close()
        return None
    runtime._node_host = node_runtime  # noqa: SLF001 - composition-root wiring
    return node_runtime


__all__ = ["BootstrapConfig", "ProductBootstrap", "attach_node_host", "bootstrap"]
