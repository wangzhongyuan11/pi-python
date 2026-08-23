"""Agent-independent validated theme data consumed by terminal adapters."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

type ThemeColor = str | int


@dataclass(frozen=True, slots=True, kw_only=True)
class Theme:
    name: str
    colors: Mapping[str, ThemeColor]
    export_colors: Mapping[str, ThemeColor]


def create_theme(
    *,
    name: str,
    colors: Mapping[str, ThemeColor],
    export_colors: Mapping[str, ThemeColor] | None = None,
) -> Theme:
    return Theme(
        name=name,
        colors=MappingProxyType(dict(colors)),
        export_colors=MappingProxyType(dict(export_colors or {})),
    )


__all__ = ["Theme", "ThemeColor", "create_theme"]
