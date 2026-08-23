"""Synchronous layered settings loader."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from pydantic import ValidationError

from .models import KNOWN_SETTING_ALIASES, SettingsValidationError, SettingsValues


def _merge(base: dict[str, Any], overrides: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overrides.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, Mapping):
            merged[key] = _merge(cast(dict[str, Any], current), cast(Mapping[str, Any], value))
        else:
            merged[key] = value
    return merged


def _read(path: Path, scope: str) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SettingsValidationError(
            f"invalid {scope} settings at {path.resolve()}: {error}"
        ) from error
    if not isinstance(value, dict):
        raise SettingsValidationError(
            f"invalid {scope} settings at {path.resolve()}: expected a JSON object"
        )
    return cast(dict[str, Any], value)


def _split_unknown(
    payload: Mapping[str, Any], scope: str, warnings: list[str]
) -> tuple[dict[str, Any], dict[str, Any]]:
    known: dict[str, Any] = {}
    unknown: dict[str, Any] = {}
    for key, value in payload.items():
        target = known if key in KNOWN_SETTING_ALIASES else unknown
        target[key] = value
        if target is unknown:
            warnings.append(f"unknown {scope} setting preserved: {key}")
    return known, unknown


@dataclass(frozen=True, slots=True, kw_only=True)
class SettingsManager:
    values: SettingsValues
    compatibility: dict[str, Any]
    warnings: tuple[str, ...]
    _resource_bases: dict[str, Path]

    @classmethod
    def load(
        cls,
        *,
        agent_dir: Path,
        cwd: Path,
        project_trusted: bool = False,
        environment_overrides: Mapping[str, Any] | None = None,
        cli_overrides: Mapping[str, Any] | None = None,
    ) -> SettingsManager:
        resolved_agent = agent_dir.resolve()
        resolved_cwd = cwd.resolve()
        layers: list[tuple[str, Path, dict[str, Any]]] = [
            ("global", resolved_agent, _read(resolved_agent / "settings.json", "global"))
        ]
        if project_trusted:
            layers.append(
                (
                    "project",
                    resolved_cwd,
                    _read(resolved_cwd / ".pi-python" / "settings.json", "project"),
                )
            )
        if environment_overrides:
            layers.append(("environment", resolved_cwd, dict(environment_overrides)))
        if cli_overrides:
            layers.append(("CLI", resolved_cwd, dict(cli_overrides)))

        merged: dict[str, Any] = {}
        compatibility: dict[str, Any] = {}
        warnings: list[str] = []
        resource_bases: dict[str, Path] = {}
        values = SettingsValues()
        for scope, base, payload in layers:
            if scope == "project" and "defaultProjectTrust" in payload:
                payload = dict(payload)
                payload.pop("defaultProjectTrust")
                warnings.append("project setting ignored: defaultProjectTrust is global-only")
            known, unknown = _split_unknown(payload, scope, warnings)
            merged = _merge(merged, known)
            compatibility = _merge(compatibility, unknown)
            for key in ("extensions", "skills", "prompts", "themes"):
                if key in known:
                    resource_bases[key] = base
            try:
                values = SettingsValues.model_validate(merged)
            except ValidationError as error:
                location = (
                    base / "settings.json"
                    if scope == "global"
                    else base / ".pi-python" / "settings.json"
                )
                raise SettingsValidationError(
                    f"invalid {scope} settings at {location.resolve()}: "
                    f"{error.errors(include_input=False)}"
                ) from error
        return cls(
            values=values,
            compatibility=compatibility,
            warnings=tuple(warnings),
            _resource_bases=resource_bases,
        )

    def resource_paths(self, kind: str) -> tuple[Path, ...]:
        if kind not in {"extensions", "skills", "prompts", "themes"}:
            raise KeyError(kind)
        values = cast(tuple[str, ...], getattr(self.values, kind))
        base = self._resource_bases.get(kind, Path.cwd().resolve())
        return tuple(
            (base / value).resolve() if not Path(value).is_absolute() else Path(value).resolve()
            for value in values
        )


__all__ = ["SettingsManager"]
