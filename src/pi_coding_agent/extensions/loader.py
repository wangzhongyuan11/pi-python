"""Two-phase extension loading: enumerate manifests, import only when trusted."""

from __future__ import annotations

import hashlib
import sys
import types
from dataclasses import dataclass
from pathlib import Path

from .metadata import (
    MANIFEST_NAME,
    MAX_MANIFEST_BYTES,
    ExtensionManifestError,
    ExtensionMetadata,
    read_manifest,
)


class ExtensionNotTrustedError(RuntimeError):
    """Loading was requested before the extension was granted trust."""


MAX_ENTRY_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ExtensionIdentity:
    name: str
    version: str
    entry: str
    path: Path
    manifest_hash: str
    entry_hash: str


def discover_extensions(root: Path) -> tuple[ExtensionMetadata, ...]:
    """Enumerate valid extension manifests under ``root`` without importing code."""
    discovered: list[ExtensionMetadata] = []
    if not root.is_dir():
        return ()
    for child in sorted(root.iterdir()):
        if not child.is_dir() or not (child / MANIFEST_NAME).exists():
            continue
        try:
            discovered.append(read_manifest(child))
        except ExtensionManifestError:
            continue
    return tuple(discovered)


class ExtensionLoader:
    """Imports trusted extension entry modules exactly once per session."""

    __slots__ = ("_loaded", "_trusted")

    def __init__(self) -> None:
        self._trusted: set[ExtensionIdentity] = set()
        self._loaded: dict[ExtensionIdentity, types.ModuleType] = {}

    def grant_trust(self, metadata: ExtensionMetadata) -> None:
        self._trusted.add(_identity(metadata))

    def is_trusted(self, metadata: ExtensionMetadata) -> bool:
        try:
            identity = _identity(metadata)
        except (ImportError, ExtensionManifestError, OSError):
            return False
        return identity in self._trusted

    def load(self, metadata: ExtensionMetadata) -> types.ModuleType:
        try:
            identity, entry_bytes = _identity_and_source(metadata)
        except (ImportError, ExtensionManifestError, OSError) as error:
            raise ExtensionNotTrustedError(
                f"extension {metadata.name!r} identity is no longer valid"
            ) from error
        if identity not in self._trusted:
            raise ExtensionNotTrustedError(
                f"extension {metadata.name!r} has not been granted trust"
            )
        cached = self._loaded.get(identity)
        if cached is not None:
            return cached
        module = self._import_entry(metadata, identity, entry_bytes)
        self._loaded[identity] = module
        return module

    def _import_entry(
        self, metadata: ExtensionMetadata, identity: ExtensionIdentity, entry_bytes: bytes
    ) -> types.ModuleType:
        entry_path = (metadata.path / metadata.entry).resolve()
        module_name = f"pi_extension_{identity.manifest_hash[:12]}_{identity.entry_hash[:12]}"
        module = types.ModuleType(module_name)
        module.__file__ = str(entry_path)
        module.__package__ = ""
        sys.modules[module_name] = module
        try:
            code = compile(entry_bytes, str(entry_path), "exec")
            exec(code, module.__dict__)
        except BaseException:
            if sys.modules.get(module_name) is module:
                del sys.modules[module_name]
            raise
        return module


def _identity(metadata: ExtensionMetadata) -> ExtensionIdentity:
    identity, _entry_bytes = _identity_and_source(metadata)
    return identity


def _identity_and_source(metadata: ExtensionMetadata) -> tuple[ExtensionIdentity, bytes]:
    current = read_manifest(metadata.path)
    if current != metadata:
        raise ExtensionManifestError(f"extension manifest changed: {metadata.path}")
    entry_path = (metadata.path / metadata.entry).resolve()
    if not entry_path.is_file():
        raise ImportError(f"extension {metadata.name!r} entry is missing: {entry_path}")
    try:
        with entry_path.open("rb") as stream:
            entry_bytes = stream.read(MAX_ENTRY_BYTES + 1)
        if len(entry_bytes) > MAX_ENTRY_BYTES:
            raise ImportError(f"extension {metadata.name!r} entry exceeds size limit")
        with (metadata.path / MANIFEST_NAME).open("rb") as stream:
            manifest_bytes = stream.read(MAX_MANIFEST_BYTES + 1)
        if len(manifest_bytes) > MAX_MANIFEST_BYTES:
            raise ImportError(f"extension {metadata.name!r} manifest exceeds size limit")
    except OSError as error:
        raise ImportError(f"extension {metadata.name!r} identity is unreadable") from error
    identity = ExtensionIdentity(
        name=metadata.name,
        version=metadata.version,
        entry=metadata.entry,
        path=metadata.path,
        manifest_hash=hashlib.sha256(manifest_bytes).hexdigest(),
        entry_hash=hashlib.sha256(entry_bytes).hexdigest(),
    )
    return identity, entry_bytes


__all__ = [
    "ExtensionIdentity",
    "ExtensionLoader",
    "ExtensionNotTrustedError",
    "MAX_ENTRY_BYTES",
    "discover_extensions",
]
