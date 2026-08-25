"""Opt-in PowerShell tool provider, available only on Windows."""

from __future__ import annotations

import sys


class PowerShellExtension:
    """Disabled by default; usable only when the platform is Windows."""

    __slots__ = ("_enabled", "_platform")

    def __init__(self, *, platform: str | None = None) -> None:
        self._platform = platform if platform is not None else sys.platform
        self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def available(self) -> bool:
        return self._enabled and self._platform == "win32"

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False


__all__ = ["PowerShellExtension"]
