"""Two-phase extension loading: enumerate manifests, import only when trusted."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

from .metadata import MANIFEST_NAME, ExtensionManifestError, ExtensionMetadata, read_manifest


class ExtensionNotTrustedError(RuntimeError):
    """Loading was requested before the extension was granted trust."""


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
        self._trusted: set[str] = set()
        self._loaded: dict[str, types.ModuleType] = {}

    def grant_trust(self, name: str) -> None:
        self._trusted.add(name)

    def is_trusted(self, name: str) -> bool:
        return name in self._trusted

    def load(self, metadata: ExtensionMetadata) -> types.ModuleType:
        if metadata.name not in self._trusted:
            raise ExtensionNotTrustedError(
                f"extension {metadata.name!r} has not been granted trust"
            )
        cached = self._loaded.get(metadata.name)
        if cached is not None:
            return cached
        module = self._import_entry(metadata)
        self._loaded[metadata.name] = module
        return module

    def _import_entry(self, metadata: ExtensionMetadata) -> types.ModuleType:
        entry_path = metadata.path / metadata.entry
        if not entry_path.is_file():
            raise ImportError(f"extension {metadata.name!r} entry is missing: {entry_path}")
        module_name = f"pi_extension_{metadata.name}"
        spec = importlib.util.spec_from_file_location(module_name, entry_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load extension entry: {entry_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module


__all__ = ["ExtensionLoader", "ExtensionNotTrustedError", "discover_extensions"]
