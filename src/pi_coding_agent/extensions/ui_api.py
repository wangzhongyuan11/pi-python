"""UI bridge, renderer, and session-action ports for extensions."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from .hooks import HookOutcome, invoke_hook
from .registry import RegistryConflictError


class UiBridge(Protocol):
    def show_message(self, text: str) -> None: ...

    def request_input(self, prompt: str) -> str | None: ...

    def request_confirmation(self, prompt: str) -> bool | None: ...


class UiUnavailableError(RuntimeError):
    """A UI interaction was requested while no UI bridge is attached."""


class ExtensionUiApi:
    """Delegates UI interactions to the attached bridge; safe when absent."""

    __slots__ = ("_bridge", "_renderers", "_session_actions")

    def __init__(self) -> None:
        self._bridge: UiBridge | None = None
        self._renderers: dict[str, Callable[..., object]] = {}
        self._session_actions: dict[str, Callable[..., object]] = {}

    def bind(self, bridge: UiBridge | None) -> None:
        self._bridge = bridge

    def _require_bridge(self) -> UiBridge:
        if self._bridge is None:
            raise UiUnavailableError("no UI bridge is attached to this session")
        return self._bridge

    def show_message(self, text: str) -> None:
        self._require_bridge().show_message(text)

    def request_input(self, prompt: str) -> str | None:
        return self._require_bridge().request_input(prompt)

    def request_confirmation(self, prompt: str) -> bool | None:
        return self._require_bridge().request_confirmation(prompt)

    def register_renderer(self, kind: str, renderer: Callable[..., object]) -> None:
        if kind in self._renderers:
            raise RegistryConflictError(f"renderer {kind!r} already registered")
        self._renderers[kind] = renderer

    def register_session_action(self, name: str, handler: Callable[..., object]) -> None:
        if name in self._session_actions:
            raise RegistryConflictError(f"session action {name!r} already registered")
        self._session_actions[name] = handler

    async def render(self, kind: str, payload: object) -> HookOutcome:
        renderer = self._renderers.get(kind)
        if renderer is None:
            return HookOutcome(ok=False, error=LookupError(f"no renderer for {kind!r}"))
        return await invoke_hook(renderer, payload)

    async def run_session_action(self, name: str) -> HookOutcome:
        handler = self._session_actions.get(name)
        if handler is None:
            return HookOutcome(ok=False, error=LookupError(f"no session action {name!r}"))
        return await invoke_hook(handler)


__all__ = ["ExtensionUiApi", "UiBridge", "UiUnavailableError"]
