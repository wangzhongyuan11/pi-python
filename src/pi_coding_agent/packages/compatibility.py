"""Static compatibility reporting for installed Pi packages."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ..extensions.metadata import MANIFEST_NAME
from .manifest import read_package_manifest

type CompatibilityLevel = Literal["native", "portable", "bridged", "unsupported"]

_NODE_SUFFIXES = frozenset({".js", ".ts", ".mjs", ".mts", ".cjs", ".cts"})
_CUSTOM_TUI_MARKERS = ("@earendil-works/pi-tui", ".ui.custom(", "ctx.ui.custom(")


@dataclass(frozen=True, slots=True)
class PackageCapability:
    kind: str
    path: str
    level: CompatibilityLevel
    reason: str


@dataclass(frozen=True, slots=True)
class PackageCompatibility:
    package_name: str
    overall: CompatibilityLevel
    capabilities: tuple[PackageCapability, ...]


def inspect_package(package_root: Path) -> PackageCompatibility:
    root = package_root.resolve()
    manifest = read_package_manifest(root)
    capabilities: list[PackageCapability] = []
    for resource in manifest.resources:
        relative = resource.path.relative_to(root).as_posix()
        if resource.kind != "extension":
            capabilities.append(
                PackageCapability(
                    kind=resource.kind,
                    path=relative,
                    level="portable",
                    reason="resource is loaded directly by pi-python",
                )
            )
            continue
        capabilities.extend(_extension_capabilities(root, resource.path))
    capabilities.sort(key=lambda item: (item.path, item.kind, item.level))
    return PackageCompatibility(
        package_name=manifest.package_name,
        overall=_overall(capabilities),
        capabilities=tuple(capabilities),
    )


def _extension_capabilities(root: Path, path: Path) -> list[PackageCapability]:
    if path.is_file():
        return [_extension_file(root, path)]
    if (path / MANIFEST_NAME).is_file():
        return [_native_extension(root, path)]
    native_dirs = sorted(
        {manifest.parent for manifest in path.rglob(MANIFEST_NAME)},
        key=lambda item: item.as_posix(),
    )
    capabilities = [_native_extension(root, directory) for directory in native_dirs]
    for candidate in sorted(path.rglob("*"), key=lambda item: item.as_posix()):
        if not candidate.is_file() or candidate.suffix.casefold() not in _NODE_SUFFIXES:
            continue
        if any(candidate.is_relative_to(directory) for directory in native_dirs):
            continue
        capabilities.append(_extension_file(root, candidate))
    if not capabilities:
        capabilities.append(_unsupported_extension(root, path))
    return capabilities


def _native_extension(root: Path, path: Path) -> PackageCapability:
    return PackageCapability(
        kind="extension",
        path=path.relative_to(root).as_posix(),
        level="native",
        reason="Python extension manifest is executed by the native runtime",
    )


def _extension_file(root: Path, path: Path) -> PackageCapability:
    relative = path.relative_to(root).as_posix()
    if path.suffix.casefold() not in _NODE_SUFFIXES:
        return _unsupported_extension(root, path)
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return PackageCapability(
            kind="extension",
            path=relative,
            level="unsupported",
            reason="extension source is unreadable",
        )
    if any(marker in source for marker in _CUSTOM_TUI_MARKERS):
        return PackageCapability(
            kind="extension",
            path=relative,
            level="unsupported",
            reason="custom upstream TUI components cannot cross the Node bridge",
        )
    return PackageCapability(
        kind="extension",
        path=relative,
        level="bridged",
        reason="JavaScript/TypeScript extension requires the Node host",
    )


def _unsupported_extension(root: Path, path: Path) -> PackageCapability:
    return PackageCapability(
        kind="extension",
        path=path.relative_to(root).as_posix(),
        level="unsupported",
        reason="extension entry is neither a Python manifest nor JavaScript/TypeScript",
    )


def _overall(capabilities: list[PackageCapability]) -> CompatibilityLevel:
    levels = {item.level for item in capabilities}
    for level in ("unsupported", "bridged", "native", "portable"):
        if level in levels:
            return level
    return "portable"


__all__ = [
    "CompatibilityLevel",
    "PackageCapability",
    "PackageCompatibility",
    "inspect_package",
]
