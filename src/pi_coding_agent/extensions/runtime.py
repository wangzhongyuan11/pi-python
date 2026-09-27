"""Concrete extension runtime composed from discovery, trust, API, and lifecycle."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from pi_agent import AgentTool
from pi_ai import Provider
from pi_tui import UI

from ..ports import ResourceDescriptor
from ..resources.default_loader import DefaultResourceLoader
from .api import ExtensionAPI
from .auth_api import ExtensionAuthApi, MemoryCredentialStore
from .context import ExtensionActions, ExtensionCommandInfo
from .hooks import ApplyHookResult, HookOutcome, HookRunner
from .lifecycle import ExtensionLifecycle
from .loader import ExtensionLoader
from .metadata import ExtensionMetadata
from .registry import CapabilityRegistry, ExtensionFlagError, FlagState
from .renderers import ExtensionRendererRegistry
from .session_context import SessionShutdownEvent, SessionStartEvent
from .ui_api import ExtensionUiApi


class DefaultExtensionRuntime:
    """Loads only explicitly trusted Python extensions and isolates startup failures."""

    __slots__ = (
        "_cwd",
        "_actions",
        "_applied_flags",
        "_auth_stores",
        "_auth_apis",
        "_descriptors",
        "_diagnostics",
        "_hooks",
        "_lifecycle",
        "_loader",
        "_registry",
        "_renderers",
        "_resources",
        "_session_binding",
        "_started",
        "_product_ui",
        "_ui_apis",
    )

    def __init__(
        self, *, cwd: Path, resources: DefaultResourceLoader, ui: UI | None = None
    ) -> None:
        self._cwd = cwd.resolve()
        self._actions = ExtensionActions()
        self._applied_flags: dict[str, bool | str] = {}
        self._product_ui = ui
        self._ui_apis: list[ExtensionUiApi] = []
        self._auth_stores: dict[str, MemoryCredentialStore] = {}
        self._auth_apis: list[ExtensionAuthApi] = []
        self._renderers = ExtensionRendererRegistry()
        self._resources = resources
        self._loader = ExtensionLoader()
        self._registry = CapabilityRegistry()
        self._hooks = HookRunner()
        self._lifecycle = ExtensionLifecycle()
        self._descriptors: tuple[ResourceDescriptor, ...] = ()
        self._diagnostics: list[str] = []
        self._started = False
        self._session_binding: tuple[object, object, tuple[AgentTool[Any, Any], ...]] | None = None

    @property
    def registry(self) -> CapabilityRegistry:
        return self._registry

    def register_hook(self, event: str, handler: Callable[..., object]) -> Callable[[], None]:
        """Register an ordered handler on the shared hook runner.

        Used by cross-runtime bridges (the Node extension host) so that
        bridged handlers participate in the same ordered fan-out as native
        Python extensions.
        """

        return self._hooks.register(event, handler)

    @property
    def diagnostics(self) -> tuple[str, ...]:
        return tuple(self._diagnostics)

    @property
    def renderers(self) -> ExtensionRendererRegistry:
        return self._renderers

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

    @property
    def actions(self) -> ExtensionActions:
        return self._actions

    def bind_session(
        self,
        *,
        session: object,
        model_runtime: object,
        all_tools: tuple[AgentTool[Any, Any], ...],
    ) -> None:
        from ..agent_session import AgentSession
        from ..model_runtime import ModelRuntime

        if not isinstance(session, AgentSession) or not isinstance(model_runtime, ModelRuntime):
            raise TypeError("extension actions require the product session and model runtime")
        self._session_binding = (session, model_runtime, all_tools)
        self._actions.bind(
            session=session,
            model_runtime=model_runtime,
            all_tools=all_tools,
            tool_sources={item.name: item.source for item in self._registry.registrations("tool")},
            commands=tuple(
                ExtensionCommandInfo(name=item.name, source=item.source)
                for item in self._registry.registrations("command")
            ),
            project_trusted=self._resources.last_result.project_trusted,
        )

    def apply_flags(self, values: dict[str, bool | str]) -> None:
        """Apply only flags claimed by the activated extension registry."""

        unknown: list[str] = []
        errors: list[str] = []
        for name, value in values.items():
            flag_name = name if name.startswith("--") else f"--{name}"
            registration = self._registry.lookup("flag", flag_name)
            if registration is None or not isinstance(registration.payload, FlagState):
                unknown.append(flag_name)
                continue
            state = registration.payload
            if state.value_type == "boolean":
                state.set(True)
            elif isinstance(value, str):
                state.set(value)
            else:
                errors.append(f'Extension flag "{flag_name}" requires a value')
        if unknown:
            errors.append(f"unrecognized arguments: {' '.join(unknown)}")
        if errors:
            raise ExtensionFlagError("; ".join(errors))
        self._applied_flags.update(values)

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
            self._actions = ExtensionActions()
            self._ui_apis = []
            self._auth_apis = []
            self._renderers = ExtensionRendererRegistry()
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
        self._actions.terminate_exec_processes()
        errors = await self._lifecycle.teardown_async()
        self._diagnostics.extend(f"extension teardown failed: {error}" for error in errors)
        self._actions.invalidate()
        for ui in self._ui_apis:
            ui.invalidate()
        for auth in self._auth_apis:
            auth.invalidate()
        self._renderers.invalidate()
        self._started = False

    async def reload(self) -> tuple[ResourceDescriptor, ...]:
        """Replace this runtime generation while preserving its session binding."""

        binding = self._session_binding
        if self._started:
            await self.emit(SessionShutdownEvent(reason="reload"))
        await self.close()
        descriptors = await self.start()
        if self._applied_flags:
            self.apply_flags(dict(self._applied_flags))
        if binding is not None:
            session, model_runtime, all_tools = binding
            self.bind_session(
                session=session,
                model_runtime=model_runtime,
                all_tools=all_tools,
            )
        await self.emit(SessionStartEvent(reason="reload"))
        return descriptors

    async def _activate(self, metadata: ExtensionMetadata) -> None:
        api: ExtensionAPI | None = None
        auth: ExtensionAuthApi | None = None
        ui: ExtensionUiApi | None = None
        try:
            module = self._loader.load(metadata)
            factory = getattr(module, "activate", None)
            if not callable(factory):
                raise TypeError("extension entry must define callable activate(api)")
            auth = ExtensionAuthApi(
                store=self._auth_stores.setdefault(metadata.name, MemoryCredentialStore())
            )
            self._auth_apis.append(auth)
            ui = ExtensionUiApi(product_ui=self._product_ui)
            self._ui_apis.append(ui)
            api = ExtensionAPI(
                metadata.name,
                registry=self._registry,
                hooks=self._hooks,
                actions=self._actions,
                ui=ui,
                auth=auth,
                renderers=self._renderers,
            )
            teardown = factory(api)
            if inspect.isawaitable(teardown):
                teardown = await teardown
            if teardown is not None:
                if not callable(teardown):
                    raise TypeError("extension activate() must return a teardown callable or None")
                self._lifecycle.register_teardown(_as_teardown(teardown))
        except Exception as error:
            if api is not None:
                api.rollback_activation()
            if auth is not None:
                auth.invalidate()
            if ui is not None:
                ui.invalidate()
            self._registry.remove_source(metadata.name)
            self._renderers.remove_source(metadata.name)
            self._diagnostics.append(f"extension {metadata.name!r} failed: {error}")


def _as_teardown(handler: Callable[..., object]) -> Callable[[], object]:
    return lambda: handler()


__all__ = ["DefaultExtensionRuntime"]
