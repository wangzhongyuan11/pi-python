"""Registration facade handed to a single extension."""

from __future__ import annotations

from typing import Literal

from .registry import CapabilityRegistry, FlagState, Registration, RegistrationKind


class ExtensionAPI:
    """Registers capabilities on behalf of one extension into one registry."""

    __slots__ = ("_name", "_registry")

    def __init__(self, name: str, *, registry: CapabilityRegistry | None = None) -> None:
        self._name = name
        self._registry = registry if registry is not None else CapabilityRegistry()

    @property
    def registry(self) -> CapabilityRegistry:
        return self._registry

    def _define(
        self, kind: RegistrationKind, name: str, payload: object | None = None
    ) -> Registration:
        return self._registry.register(kind, name, self._name, payload)

    def define_tool(self, name: str, tool: object | None = None) -> Registration:
        return self._define("tool", name, tool)

    def define_command(self, name: str, handler: object | None = None) -> Registration:
        return self._define("command", name, handler)

    def define_provider(self, name: str, provider: object | None = None) -> Registration:
        return self._define("provider", name, provider)

    def define_flag(
        self,
        name: str,
        *,
        value_type: Literal["boolean", "string"] = "boolean",
        default: bool | str | None = None,
    ) -> Registration:
        state = FlagState(value_type=value_type, value=None)
        state.set(default)
        return self._define("flag", name, state)

    def get_flag(self, name: str) -> bool | str | None:
        registration = self._registry.lookup("flag", name)
        if registration is None or registration.source != self._name:
            return None
        state = registration.payload
        return state.value if isinstance(state, FlagState) else None

    def set_flag(self, name: str, value: bool | str | None) -> None:
        registration = self._registry.lookup("flag", name)
        if registration is None or registration.source != self._name:
            raise LookupError(f"flag {name!r} is not registered by {self._name!r}")
        state = registration.payload
        if not isinstance(state, FlagState):
            raise TypeError(f"flag {name!r} has no mutable state")
        state.set(value)

    def define_shortcut(self, name: str, handler: object | None = None) -> Registration:
        return self._define("shortcut", name, handler)


__all__ = ["ExtensionAPI"]
