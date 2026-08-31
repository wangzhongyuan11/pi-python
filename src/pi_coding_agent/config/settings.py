"""Synchronous layered settings loader."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from pydantic import ValidationError

from pi_ai import JsonValue
from pi_coding_agent.session.atomic import atomic_write

from .models import (
    KNOWN_SETTING_ALIASES,
    PackageSource,
    SettingsValidationError,
    SettingsValues,
    settings_payload,
)


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


@dataclass(slots=True, kw_only=True)
class SettingsManager:
    values: SettingsValues
    compatibility: dict[str, Any]
    warnings: tuple[str, ...]
    _resource_bases: dict[str, Path]
    _agent_dir: Path
    _cwd: Path
    _project_trusted: bool
    _environment_overrides: dict[str, Any]
    _cli_overrides: dict[str, Any]
    _runtime_overrides: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())

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
            _agent_dir=resolved_agent,
            _cwd=resolved_cwd,
            _project_trusted=project_trusted,
            _environment_overrides=dict(environment_overrides or {}),
            _cli_overrides=dict(cli_overrides or {}),
        )

    @property
    def project_trusted(self) -> bool:
        return self._project_trusted

    @property
    def agent_dir(self) -> Path:
        return self._agent_dir

    @property
    def cwd(self) -> Path:
        return self._cwd

    def reload(self, *, project_trusted: bool | None = None) -> None:
        """Atomically reload file layers while preserving this manager's identity."""
        next_trust = self._project_trusted if project_trusted is None else project_trusted
        loaded = type(self).load(
            agent_dir=self._agent_dir,
            cwd=self._cwd,
            project_trusted=next_trust,
            environment_overrides=self._environment_overrides,
            cli_overrides=_merge(self._cli_overrides, self._runtime_overrides),
        )
        self.values = loaded.values
        self.compatibility = loaded.compatibility
        self.warnings = loaded.warnings
        self._resource_bases = loaded._resource_bases
        self._project_trusted = next_trust

    def get(self, key: str, default: JsonValue = None) -> JsonValue:
        return self.snapshot().get(key, default)

    def set(self, key: str, value: JsonValue) -> None:
        self._runtime_overrides[key] = value
        self.reload()

    def snapshot(self) -> dict[str, JsonValue]:
        snapshot = cast(dict[str, JsonValue], settings_payload(self.values))
        snapshot.update(cast(dict[str, JsonValue], self.compatibility))
        return snapshot

    def package_sources(self, scope: str) -> tuple[str | PackageSource, ...]:
        if scope == "project" and not self._project_trusted:
            return ()
        path, label = self._package_settings_path(scope)
        payload = _read(path, label)
        try:
            return SettingsValues.model_validate({"packages": payload.get("packages", [])}).packages
        except ValidationError as error:
            raise SettingsValidationError(
                f"invalid {label} settings at {path}: {error.errors(include_input=False)}"
            ) from error

    def set_package_sources(
        self,
        sources: tuple[str | PackageSource, ...],
        *,
        scope: str,
    ) -> None:
        if scope == "project" and not self._project_trusted:
            raise PermissionError("project trust is required to change project packages")
        path, label = self._package_settings_path(scope)
        validated = SettingsValues.model_validate({"packages": sources}).packages
        payload = _read(path, label)
        payload["packages"] = [
            source if isinstance(source, str) else source.model_dump(by_alias=True, mode="json")
            for source in validated
        ]
        data = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        atomic_write(path, data)
        self.reload()

    def _package_settings_path(self, scope: str) -> tuple[Path, str]:
        if scope == "user":
            return self._agent_dir / "settings.json", "global"
        if scope == "project":
            return self._cwd / ".pi-python" / "settings.json", "project"
        raise ValueError(f"unsupported package scope: {scope}")

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
