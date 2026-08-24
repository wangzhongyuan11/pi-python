"""Registration facade handed to a single extension."""

from __future__ import annotations

from .registry import CapabilityRegistry, Registration, RegistrationKind


class ExtensionAPI:
    """Registers capabilities on behalf of one extension into one registry."""

    __slots__ = ("_name", "_registry")

    def __init__(self, name: str, *, registry: CapabilityRegistry | None = None) -> None:
        self._name = name
        self._registry = registry if registry is not None else CapabilityRegistry()

    @property
    def registry(self) -> CapabilityRegistry:
        return self._registry

    def _define(self, kind: RegistrationKind, name: str) -> Registration:
        return self._registry.register(kind, name, self._name)

    def define_tool(self, name: str) -> Registration:
        return self._define("tool", name)

    def define_command(self, name: str) -> Registration:
        return self._define("command", name)

    def define_provider(self, name: str) -> Registration:
        return self._define("provider", name)

    def define_flag(self, name: str) -> Registration:
        return self._define("flag", name)

    def define_shortcut(self, name: str) -> Registration:
        return self._define("shortcut", name)


__all__ = ["ExtensionAPI"]
