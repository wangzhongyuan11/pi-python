"""Extension manifest parsing: pure metadata, never executes code."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

MANIFEST_NAME = "pi-extension.json"
MAX_MANIFEST_BYTES = 64 * 1024


class ExtensionManifestError(ValueError):
    """A manifest is missing, unreadable, or does not match the schema."""


@dataclass(frozen=True, slots=True)
class ExtensionMetadata:
    name: str
    version: str
    entry: str
    path: Path


def read_manifest(extension_dir: Path) -> ExtensionMetadata:
    extension_path = extension_dir.resolve()
    manifest_path = extension_path / MANIFEST_NAME
    try:
        if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
            raise ExtensionManifestError(f"manifest exceeds size limit: {manifest_path}")
        raw = manifest_path.read_text(encoding="utf-8")
    except OSError as error:
        raise ExtensionManifestError(f"missing manifest: {manifest_path}") from error
    try:
        payload: object = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ExtensionManifestError(f"invalid JSON in {manifest_path}") from error
    if not isinstance(payload, dict):
        raise ExtensionManifestError(f"manifest must be an object: {manifest_path}")
    record = cast("dict[str, object]", payload)
    fields: dict[str, str] = {}
    for field in ("name", "version", "entry"):
        value = record.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ExtensionManifestError(f"manifest field {field!r} must be a non-empty string")
        fields[field] = value
    entry_path = (extension_path / fields["entry"]).resolve()
    if not entry_path.is_relative_to(extension_path):
        raise ExtensionManifestError(f"manifest entry escapes extension directory: {manifest_path}")
    return ExtensionMetadata(
        name=fields["name"],
        version=fields["version"],
        entry=fields["entry"],
        path=extension_path,
    )


__all__ = [
    "ExtensionManifestError",
    "ExtensionMetadata",
    "MANIFEST_NAME",
    "MAX_MANIFEST_BYTES",
    "read_manifest",
]
