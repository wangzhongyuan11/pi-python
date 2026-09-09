"""Validated Pi resource manifests for installed packages."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from pi_coding_agent.config.models import PackageSource
from pi_coding_agent.ports import ResourceKind, ResourceRoot

_PACKAGE_NAME = re.compile(
    r"^(?:[A-Za-z0-9][A-Za-z0-9._-]*|@[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*)$"
)
_RESOURCE_FIELDS: tuple[tuple[str, ResourceKind], ...] = (
    ("extensions", "extension"),
    ("skills", "skill"),
    ("prompts", "prompt"),
    ("themes", "theme"),
)


class PackageManifestError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PackageManifest:
    name: str
    package_name: str
    resources: tuple[ResourceRoot, ...]


def read_package_manifest(
    package_root: Path, *, package_filter: PackageSource | None = None
) -> PackageManifest:
    root = package_root.resolve()
    manifest_path = root / "package.json"
    try:
        raw: object = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PackageManifestError(
            f"invalid package manifest at {manifest_path}: {error}"
        ) from error
    if not isinstance(raw, dict):
        raise PackageManifestError("package manifest must be a JSON object")
    payload = cast(dict[str, object], raw)
    package_name = payload.get("name")
    if not isinstance(package_name, str) or not _PACKAGE_NAME.fullmatch(package_name):
        raise PackageManifestError("package manifest requires a safe name")
    name = package_name.lstrip("@").replace("/", "--")
    pi = payload.get("pi")
    if pi is not None and not isinstance(pi, dict):
        raise PackageManifestError("package manifest pi field must be an object")
    roots: list[ResourceRoot] = []
    for field, kind in _RESOURCE_FIELDS:
        entries = _string_entries(
            cast(dict[str, object], pi).get(field, []) if pi else [field],
            label=f"package manifest pi.{field}",
        )
        selected = _resolve_entries(root, entries, strict_exact=pi is not None)
        filter_entries = getattr(package_filter, field) if package_filter is not None else None
        if filter_entries is not None:
            selected = _apply_filter(root, selected, filter_entries)
        roots.extend(ResourceRoot(kind=kind, path=path, source="package") for path in selected)
    return PackageManifest(name=name, package_name=package_name, resources=tuple(roots))


def _string_entries(value: object, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise PackageManifestError(f"{label} must be a string array")
    items = cast("list[object]", value)
    if not all(isinstance(item, str) for item in items):
        raise PackageManifestError(f"{label} must be a string array")
    return tuple(cast("list[str]", items))


def _apply_filter(root: Path, base: tuple[Path, ...], entries: tuple[str, ...]) -> tuple[Path, ...]:
    if not entries:
        return ()
    positive = tuple(entry for entry in entries if not entry.startswith(("!", "+", "-")))
    selected = list(_resolve_entries(root, positive, strict_exact=False) if positive else base)
    for entry in entries:
        if entry.startswith("!"):
            excluded = set(_resolve_entries(root, (entry[1:],), strict_exact=False))
            selected = [path for path in selected if path not in excluded]
        elif entry.startswith("-"):
            candidate = _safe_candidate(root, entry[1:])
            selected = [path for path in selected if path != candidate]
        elif entry.startswith("+"):
            candidate = _safe_candidate(root, entry[1:])
            if not candidate.exists():
                raise PackageManifestError(f"package resource root does not exist: {entry[1:]}")
            selected.append(candidate)
    return _dedupe_paths(selected)


def _resolve_entries(
    root: Path, entries: tuple[str, ...], *, strict_exact: bool
) -> tuple[Path, ...]:
    selected: list[Path] = []
    exclusions: list[str] = []
    for entry in entries:
        if entry.startswith("!"):
            exclusions.append(entry[1:])
            continue
        candidate = _safe_candidate(root, entry)
        if _has_glob(entry):
            selected.extend(path.resolve() for path in root.glob(entry) if path.exists())
        elif candidate.exists():
            selected.append(candidate)
        elif strict_exact:
            raise PackageManifestError(f"package resource root does not exist: {entry}")
    for pattern in exclusions:
        excluded = set(_resolve_entries(root, (pattern,), strict_exact=False))
        selected = [path for path in selected if path not in excluded]
    return _dedupe_paths(selected)


def _safe_candidate(root: Path, entry: str) -> Path:
    if not entry or Path(entry).is_absolute() or re.match(r"^[A-Za-z]:[/\\]", entry):
        raise PackageManifestError(f"resource path is outside package root: {entry}")
    candidate = (root / entry).resolve()
    if not candidate.is_relative_to(root):
        raise PackageManifestError(f"resource path is outside package root: {entry}")
    return candidate


def _has_glob(entry: str) -> bool:
    return any(character in entry for character in "*?[")


def _dedupe_paths(paths: list[Path] | tuple[Path, ...]) -> tuple[Path, ...]:
    return tuple(sorted(set(paths), key=lambda path: path.as_posix()))


__all__ = ["PackageManifest", "PackageManifestError", "read_package_manifest"]
