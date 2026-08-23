"""Deterministic descriptor enumeration with frozen source precedence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from .descriptors import ResourceDescriptor, ResourceKind, ResourceSource

_DIRECTORIES: dict[ResourceKind, str] = {
    "extension": "extensions",
    "skill": "skills",
    "prompt": "prompts",
    "theme": "themes",
}
_KINDS: tuple[ResourceKind, ...] = ("extension", "prompt", "skill", "theme")


def _empty_explicit() -> dict[ResourceKind, tuple[Path, ...]]:
    return {}


@dataclass(frozen=True, slots=True, kw_only=True)
class DiscoveryInputs:
    cwd: Path
    agent_dir: Path
    project_trusted: bool = False
    explicit: Mapping[ResourceKind, tuple[Path, ...]] = field(default_factory=_empty_explicit)
    compatibility_root: Path | None = None
    builtins: tuple[ResourceDescriptor, ...] = ()


def _from_paths(
    paths: tuple[Path, ...], kind: ResourceKind, source: ResourceSource
) -> tuple[ResourceDescriptor, ...]:
    descriptors = (
        ResourceDescriptor(kind=kind, name=path.stem, path=path.resolve(), source=source)
        for path in paths
        if path.is_file()
    )
    return tuple(sorted(descriptors, key=lambda item: (item.name, str(item.path))))


def _directory(root: Path, source: ResourceSource) -> tuple[ResourceDescriptor, ...]:
    result: list[ResourceDescriptor] = []
    for kind, directory_name in _DIRECTORIES.items():
        directory = root / directory_name
        if not directory.is_dir():
            continue
        result.extend(_from_paths(tuple(directory.iterdir()), kind, source))
    return tuple(sorted(result, key=lambda item: (item.kind, item.name, str(item.path))))


def discover_resources(inputs: DiscoveryInputs) -> tuple[ResourceDescriptor, ...]:
    cwd = inputs.cwd.resolve()
    layers: list[tuple[ResourceDescriptor, ...]] = []
    explicit: list[ResourceDescriptor] = []
    for kind in _KINDS:
        explicit.extend(_from_paths(tuple(inputs.explicit.get(kind, ())), kind, "explicit"))
    layers.append(tuple(explicit))
    if inputs.project_trusted:
        layers.append(_directory(cwd / ".pi-python", "project"))
    if inputs.compatibility_root is not None:
        layers.append(_directory(inputs.compatibility_root.resolve(), "compatibility"))
    layers.append(_directory(inputs.agent_dir.resolve(), "global"))
    layers.append(tuple(sorted(inputs.builtins, key=lambda item: (item.kind, item.name))))

    selected: list[ResourceDescriptor] = []
    identities: set[tuple[ResourceKind, str]] = set()
    for layer in layers:
        for descriptor in layer:
            identity = (descriptor.kind, descriptor.name)
            if identity in identities:
                continue
            identities.add(identity)
            selected.append(descriptor)
    return tuple(selected)


__all__ = ["DiscoveryInputs", "discover_resources"]
