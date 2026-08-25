"""Opt-in per-tool permission gate; disabled by default like upstream."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PermissionDecision:
    tool: str
    allowed: bool


class PermissionGate:
    """When disabled every tool runs; when enabled the confirmer decides."""

    __slots__ = ("_confirmer", "_enabled")

    def __init__(
        self,
        *,
        enabled: bool = False,
        confirmer: Callable[[str], bool] | None = None,
    ) -> None:
        self._enabled = enabled
        self._confirmer = confirmer

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self) -> None:
        self._enabled = True

    def decide(self, tool_name: str) -> PermissionDecision:
        if not self._enabled:
            return PermissionDecision(tool=tool_name, allowed=True)
        if self._confirmer is None:
            return PermissionDecision(tool=tool_name, allowed=False)
        return PermissionDecision(tool=tool_name, allowed=bool(self._confirmer(tool_name)))


__all__ = ["PermissionDecision", "PermissionGate"]
