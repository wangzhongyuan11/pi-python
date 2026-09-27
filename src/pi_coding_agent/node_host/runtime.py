"""Supervised Node extension host runtime (P15.5-T06).

Owns one Node host process per product generation. Bridged extensions
register into the shared capability registry and hook runner, so the product
surfaces treat them like native extensions. Reload tears the process down and
boots a fresh generation; crashes are recorded as diagnostics and leave no
orphaned processes behind.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import cast

from ..extensions.runtime import DefaultExtensionRuntime
from .event_bridge import (
    ExtensionActionsProtocol,
    NodeActionBridge,
    NodeEventBridge,
    combine_handlers,
)
from .models import HelloAck
from .process import DependencyInstaller, NodeHostError, NodeHostProcess
from .registry_bridge import RegistryBridge
from .ui_bridge import NodeUiBridge, NodeUiPort


class NodeHostRuntime:
    """Supervised lifecycle owner for the bridged extension generation."""

    def __init__(
        self,
        *,
        extensions_runtime: DefaultExtensionRuntime,
        cwd: Path,
        has_ui: bool = False,
        ui_provider: Callable[[], object | None] | None = None,
        actions_provider: Callable[[], object | None] | None = None,
        installer: DependencyInstaller | None = None,
    ) -> None:
        self._extensions_runtime = extensions_runtime
        self._cwd = Path(cwd)
        self._has_ui = has_ui
        self._ui_provider = ui_provider
        self._actions_provider = actions_provider
        self._installer = installer
        self._process: NodeHostProcess | None = None
        self._event_bridge: NodeEventBridge | None = None
        self._sources: tuple[str, ...] = ()
        self._generation = 0
        self._stale = False
        self._failed = False
        self._diagnostics: list[str] = []

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def failed(self) -> bool:
        return self._failed

    @property
    def diagnostics(self) -> tuple[str, ...]:
        return tuple(self._diagnostics)

    @property
    def ack(self) -> HelloAck | None:
        return self._process.ack if self._process is not None else None

    async def start(self, extension_paths: Sequence[Path]) -> HelloAck | None:
        if self._stale:
            raise NodeHostError("node host runtime generation is stale")
        if not extension_paths:
            return None
        self._generation += 1
        process = NodeHostProcess(
            extensions=list(extension_paths),
            cwd=self._cwd,
            generation=self._generation,
            state={"hasUI": self._has_ui},
            installer=self._installer,
            on_unexpected_exit=self._on_unexpected_exit,
        )
        source = self._source()
        registry_bridge = RegistryBridge(
            self._extensions_runtime.registry,
            source=source,
            host_caller=process.request,
        )
        event_bridge = NodeEventBridge(host_caller=process.request, generation=self._generation)
        ui_bridge = NodeUiBridge(
            ui_provider=cast("Callable[[], NodeUiPort | None]", self._ui_provider)
        )
        action_bridge = NodeActionBridge(
            actions_provider=cast(
                "Callable[[], ExtensionActionsProtocol | None]", self._actions_provider
            )
        )
        process.set_request_handler(combine_handlers(registry_bridge, ui_bridge, action_bridge))
        try:
            ack = await process.start()
        except NodeHostError as error:
            self._failed = True
            self._diagnostics.append(str(error))
            raise
        self._process = process
        self._event_bridge = event_bridge
        self._sources = (source,)
        self._failed = False
        subscriptions: dict[str, str] = {}
        for descriptor in ack.extensions:
            raw_events = descriptor.get("events")
            if not isinstance(raw_events, list | tuple):
                continue
            for item in cast("list[object]", raw_events):
                subscriptions[str(item)] = str(item)
        event_bridge.register_forwarders(self._extensions_runtime, subscriptions, source=source)
        return ack

    def _source(self) -> str:
        return f"node-host:{self._generation}"

    async def update_flags(self, flags: dict[str, bool | str]) -> None:
        """Push CLI flag values into the host's synchronous snapshot."""

        if self._process is not None:
            await self._process.request("update_state", {"state": {"flags": dict(flags)}})

    def _on_unexpected_exit(self, stderr: str) -> None:
        self._failed = True
        self._diagnostics.append(f"node host exited unexpectedly: {stderr[:400]}")

    async def reload(self, extension_paths: Sequence[Path]) -> HelloAck | None:
        """Tear the current generation down and boot a fresh one."""

        if self._process is not None:
            await self._process.close()
        for source in self._sources:
            self._extensions_runtime.registry.remove_source(source)
        self._event_bridge.invalidate() if self._event_bridge else None
        self._process = None
        return await self.start(extension_paths)

    async def close(self) -> None:
        self._stale = True
        if self._event_bridge is not None:
            self._event_bridge.invalidate()
        if self._process is not None:
            await self._process.close()
            self._process = None
        for source in self._sources:
            self._extensions_runtime.registry.remove_source(source)
        self._sources = ()


def discover_bridged_extensions(descriptors: object, cwd: Path) -> tuple[Path, ...]:
    """Entry paths of discovered extensions whose source is JavaScript/TypeScript.

    Extension descriptors point at the manifest directory and carry the entry
    file name; a descriptor that already points at a source file also works.
    """

    bridged: list[Path] = []
    for descriptor in getattr(descriptors, "extensions", ()) or ():
        raw_path = getattr(descriptor, "path", None)
        entry = getattr(descriptor, "entry", None)
        if raw_path is None:
            continue
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = cwd / candidate
        if candidate.is_dir():
            entry_name = str(entry) if entry else ""
            candidate = candidate / entry_name if entry_name else candidate
        if candidate.suffix.lower() in {".ts", ".js", ".mjs", ".cts", ".mts"}:
            bridged.append(candidate)
    return tuple(bridged)


__all__ = ["NodeHostRuntime", "discover_bridged_extensions"]
