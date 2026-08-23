"""Resolve product environment variables without mutating the process."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

_FALSE_VALUES = {"", "0", "false", "no", "off"}


@dataclass(frozen=True, slots=True, kw_only=True)
class EnvironmentConfig:
    agent_dir: Path | None
    session_dir: Path | None
    offline: bool
    warnings: tuple[str, ...]


def _path_value(
    environ: Mapping[str, str],
    primary: str,
    legacy: str,
    *,
    compatibility: bool,
    warnings: list[str],
) -> Path | None:
    primary_value = environ.get(primary)
    legacy_value = environ.get(legacy) if compatibility else None
    if primary_value and legacy_value:
        warnings.append(f"{primary} overrides compatibility variable {legacy}")
    selected = primary_value or legacy_value
    return None if not selected else Path(selected).expanduser().resolve()


def _enabled(value: str | None) -> bool:
    return value is not None and value.strip().casefold() not in _FALSE_VALUES


def resolve_environment(
    environ: Mapping[str, str],
    *,
    compatibility: bool = False,
) -> EnvironmentConfig:
    warnings: list[str] = []
    agent_dir = _path_value(
        environ,
        "PI_PYTHON_AGENT_DIR",
        "PI_CODING_AGENT_DIR",
        compatibility=compatibility,
        warnings=warnings,
    )
    session_dir = _path_value(
        environ,
        "PI_PYTHON_SESSION_DIR",
        "PI_CODING_AGENT_SESSION_DIR",
        compatibility=compatibility,
        warnings=warnings,
    )
    primary_offline = environ.get("PI_PYTHON_OFFLINE")
    legacy_offline = environ.get("PI_OFFLINE") if compatibility else None
    if primary_offline is not None and legacy_offline is not None:
        warnings.append("PI_PYTHON_OFFLINE overrides compatibility variable PI_OFFLINE")
    offline = _enabled(primary_offline if primary_offline is not None else legacy_offline)
    return EnvironmentConfig(
        agent_dir=agent_dir,
        session_dir=session_dir,
        offline=offline,
        warnings=tuple(warnings),
    )
