"""Path normalization and canonical mutation keys for coding tools."""

from __future__ import annotations

import os
from pathlib import Path

_UNICODE_SPACES = str.maketrans({"\u00a0": " ", "\u2007": " ", "\u202f": " "})


def _normalize_input(path: str | Path) -> str:
    value = str(path).translate(_UNICODE_SPACES)
    return value[1:] if value.startswith("@") else value


def resolve_tool_path(
    path: str | Path,
    *,
    cwd: Path,
    home: Path | None = None,
) -> Path:
    value = _normalize_input(path)
    if value == "~" or value.startswith("~/") or value.startswith("~\\"):
        base = Path.home() if home is None else home
        suffix = value[2:] if len(value) > 1 else ""
        candidate = base / suffix
    else:
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = cwd / candidate
    return candidate.resolve(strict=False)


def canonical_tool_path(path: str | Path, *, cwd: Path) -> Path:
    resolved = resolve_tool_path(path, cwd=cwd)
    return Path(os.path.normcase(os.path.realpath(resolved)))


__all__ = ["canonical_tool_path", "resolve_tool_path"]
