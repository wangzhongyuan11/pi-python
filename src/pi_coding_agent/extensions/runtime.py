"""Concrete extension runtime composed from discovery, trust, API, and lifecycle."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from pi_agent import AgentTool
from pi_ai import Provider

from ..ports import ResourceDescriptor
from ..resources.default_loader import DefaultResourceLoader
from .api import ExtensionAPI
from .hooks import ApplyHookResult, HookOutcome, HookRunner
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
        "_hooks",
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
        self._hooks = HookRunner()
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

    @property
    def tools(self) -> tuple[AgentTool[Any, Any], ...]:
        tools: list[AgentTool[Any, Any]] = []
        for registration in self._registry.registrations("tool"):
            payload: object | None = registration.payload
            if isinstance(payload, AgentTool):
                tools.append(cast("AgentTool[Any, Any]", payload))
        return tuple(tools)

    @property
    def providers(self) -> tuple[Provider, ...]:
        providers: list[Provider] = []
        for registration in self._registry.registrations("provider"):
            payload: object | None = registration.payload
            if isinstance(payload, Provider):
                providers.append(payload)
        return tuple(providers)

    def grant_trust(self, metadata: ExtensionMetadata) -> None:
        self._loader.grant_trust(metadata)

    async def emit(self, event: object) -> tuple[HookOutcome, ...]:
        event_name = getattr(event, "type", None)
        if not isinstance(event_name, str):
            raise TypeError("extension event must expose a string type")
        outcomes = tuple(await self._hooks.emit(event_name, event))
        self._diagnostics.extend(
            f"{event_name} handler failed: {outcome.error}"
            for outcome in outcomes
            if outcome.error is not None
        )
        return outcomes

    async def emit_chained(
        self, event: object, apply_result: ApplyHookResult
    ) -> tuple[HookOutcome, ...]:
        event_name = getattr(event, "type", None)
        if not isinstance(event_name, str):
            raise TypeError("extension event must expose a string type")
        outcomes = tuple(await self._hooks.emit_chained(event_name, event, apply_result))
        self._diagnostics.extend(
            f"{event_name} handler failed: {outcome.error}"
            for outcome in outcomes
            if outcome.error is not None
        )
        return outcomes

    async def start(self) -> tuple[ResourceDescriptor, ...]:
        if self._started:
            return self._descriptors
        if not self._lifecycle.active:
            self._lifecycle.begin_generation()
            self._registry = CapabilityRegistry()
            self._hooks = HookRunner()
        result = self._resources.load(cwd=self._cwd, agent_dir=self._resources.agent_dir)
        self._descriptors = tuple(
            ResourceDescriptor(
                kind="extension",
                name=metadata.name,
                path=metadata.path,
                source=self._resources.source_for("extension", metadata.path),
            )
            for metadata in result.extensions
        )
        self._diagnostics = list(result.diagnostics)
        for metadata in result.extensions:
            source = self._resources.source_for("extension", metadata.path)
            if source in {"explicit", "global", "package"} or (
                source == "project" and result.project_trusted
            ):
                self._loader.grant_trust(metadata)
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
            teardown = factory(
                ExtensionAPI(metadata.name, registry=self._registry, hooks=self._hooks)
            )
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


__all__ = ["DefaultExtensionRuntime"]
