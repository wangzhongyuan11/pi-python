"""Conflict-detecting registry for extension-provided capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RegistrationKind = Literal["tool", "command", "provider", "flag", "shortcut"]
REGISTRATION_KINDS: tuple[RegistrationKind, ...] = (
    "tool",
    "command",
    "provider",
    "flag",
    "shortcut",
)


class RegistryError(ValueError):
    """Base error for invalid or conflicting registrations."""


class RegistryInvalidNameError(RegistryError):
    """A registration name does not satisfy its kind's naming rules."""


class RegistryConflictError(RegistryError):
    """The same kind/name pair was already registered."""


@dataclass(frozen=True, slots=True)
class Registration:
    kind: RegistrationKind
    name: str
    source: str
    payload: object | None = None


@dataclass(slots=True)
class FlagState:
    value_type: Literal["boolean", "string"]
    value: bool | str | None

    def set(self, value: bool | str | None) -> None:
        if value is not None and (
            (self.value_type == "boolean" and not isinstance(value, bool))
            or (self.value_type == "string" and not isinstance(value, str))
        ):
            raise TypeError(f"expected {self.value_type} flag value")
        self.value = value


def _validate_name(kind: RegistrationKind, name: str) -> str:
    if not name.strip():
        raise RegistryInvalidNameError(f"{kind} name must be a non-empty string")
    if kind == "flag" and not name.startswith("--"):
        raise RegistryInvalidNameError(f"flag names must start with '--': {name!r}")
    return name


class CapabilityRegistry:
    """Stores registrations per kind and rejects duplicates within a kind."""

    __slots__ = ("_items",)

    def __init__(self) -> None:
        self._items: dict[tuple[RegistrationKind, str], Registration] = {}

    def register(
        self,
        kind: RegistrationKind,
        name: str,
        source: str,
        payload: object | None = None,
    ) -> Registration:
        validated = _validate_name(kind, name)
        key = (kind, validated)
        if key in self._items:
            existing = self._items[key]
            raise RegistryConflictError(
                f"{kind} {validated!r} already registered by {existing.source!r}"
            )
        registration = Registration(kind=kind, name=validated, source=source, payload=payload)
        self._items[key] = registration
        return registration

    def lookup(self, kind: RegistrationKind, name: str) -> Registration | None:
        return self._items.get((kind, name))

    def registrations(
        self,
        kind: RegistrationKind | None = None,
    ) -> tuple[Registration, ...]:
        items = [
            registration
            for (registration_kind, _), registration in sorted(self._items.items())
            if kind is None or registration_kind == kind
        ]
        return tuple(items)


__all__ = [
    "REGISTRATION_KINDS",
    "CapabilityRegistry",
    "FlagState",
    "Registration",
    "RegistrationKind",
    "RegistryConflictError",
    "RegistryError",
    "RegistryInvalidNameError",
]
