"""Explicit, read-only adapter for upstream `.pi` data resources."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .descriptors import ResourceDescriptor, ResourceKind

_DATA_DIRECTORIES: dict[ResourceKind, str] = {
    "prompt": "prompts",
    "skill": "skills",
    "theme": "themes",
}


@dataclass(frozen=True, slots=True, kw_only=True)
class PiCompatibilityResult:
    resources: tuple[ResourceDescriptor, ...]
    sessions: tuple[Path, ...]
    skipped_extensions: tuple[Path, ...]


def _files(directory: Path, pattern: str = "*") -> tuple[Path, ...]:
    if not directory.is_dir():
        return ()
    paths = (path.resolve() for path in directory.rglob(pattern) if path.is_file())
    return tuple(sorted(paths, key=str))


def discover_pi_compatibility(root: Path) -> PiCompatibilityResult:
    resolved = root.expanduser().resolve()
    if not resolved.is_dir():
        return PiCompatibilityResult(resources=(), sessions=(), skipped_extensions=())
    resources: list[ResourceDescriptor] = []
    for kind, directory_name in _DATA_DIRECTORIES.items():
        for path in _files(resolved / directory_name):
            resources.append(
                ResourceDescriptor(
                    kind=kind,
                    name=path.stem,
                    path=path,
                    source="compatibility",
                )
            )
    return PiCompatibilityResult(
        resources=tuple(sorted(resources, key=lambda item: (item.kind, item.name))),
        sessions=_files(resolved / "sessions", "*.jsonl"),
        skipped_extensions=_files(resolved / "extensions"),
    )


__all__ = ["PiCompatibilityResult", "discover_pi_compatibility"]
