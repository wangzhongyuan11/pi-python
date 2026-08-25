"""Concrete extension runtime composed from discovery, trust, API, and lifecycle."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from pathlib import Path

from ..ports import ResourceDescriptor, ResourceSource
from ..resources.default_loader import DefaultResourceLoader
from .api import ExtensionAPI
from .lifecycle import ExtensionLifecycle
from .loader import ExtensionLoader
from .metadata import ExtensionMetadata
from .registry import CapabilityRegistry


class DefaultExtensionRuntime:
    """Loads only explicitly trusted Python extensions and isolates startup failures."""

    __slots__ = (
        "_cwd",
        "_descriptors",
        "_diagnostics",
        "_lifecycle",
        "_loader",
        "_registry",
        "_resources",
        "_started",
    )

    def __init__(self, *, cwd: Path, resources: DefaultResourceLoader) -> None:
        self._cwd = cwd.resolve()
        self._resources = resources
        self._loader = ExtensionLoader()
        self._registry = CapabilityRegistry()
        self._lifecycle = ExtensionLifecycle()
        self._descriptors: tuple[ResourceDescriptor, ...] = ()
        self._diagnostics: list[str] = []
        self._started = False

    @property
    def registry(self) -> CapabilityRegistry:
        return self._registry

    @property
    def diagnostics(self) -> tuple[str, ...]:
        return tuple(self._diagnostics)

    def grant_trust(self, metadata: ExtensionMetadata) -> None:
        self._loader.grant_trust(metadata)

    async def start(self) -> tuple[ResourceDescriptor, ...]:
        if self._started:
            return self._descriptors
        if not self._lifecycle.active:
            self._lifecycle.begin_generation()
            self._registry = CapabilityRegistry()
        result = self._resources.load(cwd=self._cwd, agent_dir=self._resources.agent_dir)
        self._descriptors = tuple(
            ResourceDescriptor(
                kind="extension",
                name=metadata.name,
                path=metadata.path,
                source=_extension_source(metadata.path, self._cwd, self._resources.agent_dir),
            )
            for metadata in result.extensions
        )
        self._diagnostics = list(result.diagnostics)
        for metadata in result.extensions:
            if not self._loader.is_trusted(metadata):
                continue
            await self._activate(metadata)
        self._started = True
        return self._descriptors

    async def close(self) -> None:
        if not self._started:
            return
        errors = await self._lifecycle.teardown_async()
        self._diagnostics.extend(f"extension teardown failed: {error}" for error in errors)
        self._started = False

    async def _activate(self, metadata: ExtensionMetadata) -> None:
        try:
            module = self._loader.load(metadata)
            factory = getattr(module, "activate", None)
            if not callable(factory):
                raise TypeError("extension entry must define callable activate(api)")
            teardown = factory(ExtensionAPI(metadata.name, registry=self._registry))
            if inspect.isawaitable(teardown):
                teardown = await teardown
            if teardown is not None:
                if not callable(teardown):
                    raise TypeError("extension activate() must return a teardown callable or None")
                self._lifecycle.register_teardown(_as_teardown(teardown))
        except Exception as error:
            self._registry.remove_source(metadata.name)
            self._diagnostics.append(f"extension {metadata.name!r} failed: {error}")


def _as_teardown(handler: Callable[..., object]) -> Callable[[], object]:
    return lambda: handler()


def _extension_source(path: Path, cwd: Path, agent_dir: Path) -> ResourceSource:
    if path.is_relative_to(cwd / ".pi-python" / "extensions"):
        return "project"
    if path.is_relative_to(agent_dir / "extensions"):
        return "global"
    return "explicit"


__all__ = ["DefaultExtensionRuntime"]
