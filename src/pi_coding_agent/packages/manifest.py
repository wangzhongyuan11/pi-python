"""Validated Pi resource manifests for installed packages."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from pi_coding_agent.ports import ResourceKind, ResourceRoot

_PACKAGE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
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
    resources: tuple[ResourceRoot, ...]


def read_package_manifest(package_root: Path) -> PackageManifest:
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
    name = payload.get("name")
    if not isinstance(name, str) or not _PACKAGE_NAME.fullmatch(name):
        raise PackageManifestError("package manifest requires a safe name")
    pi = payload.get("pi")
    if pi is not None and not isinstance(pi, dict):
        raise PackageManifestError("package manifest pi field must be an object")
    roots: list[ResourceRoot] = []
    for field, kind in _RESOURCE_FIELDS:
        entries: object = (cast(dict[str, object], pi).get(field, [])) if pi else [field]
        if not isinstance(entries, list):
            raise PackageManifestError(f"package manifest pi.{field} must be a string array")
        entry_values = cast(list[object], entries)
        if not all(isinstance(item, str) for item in entry_values):
            raise PackageManifestError(f"package manifest pi.{field} must be a string array")
        for item in entry_values:
            assert isinstance(item, str)
            entry = item
            candidate = (root / entry).resolve()
            if not candidate.is_relative_to(root):
                raise PackageManifestError(f"resource path is outside package root: {entry}")
            if candidate.is_dir():
                roots.append(ResourceRoot(kind=kind, path=candidate, source="package"))
            elif pi is not None:
                raise PackageManifestError(f"package resource root does not exist: {entry}")
    return PackageManifest(name=name, resources=tuple(roots))


__all__ = ["PackageManifest", "PackageManifestError", "read_package_manifest"]
