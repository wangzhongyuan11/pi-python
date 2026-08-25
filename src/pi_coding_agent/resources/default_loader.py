"""Compose discovery, trust, packages, and extensions into one loader."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from ..extensions.loader import discover_extensions
from ..extensions.metadata import ExtensionMetadata
from ..ports import ResourceDescriptor, ResourceKind
from .descriptors import ResourceSource  # re-exported type value guard
from .discovery import DiscoveryInputs, discover_resources
from .trust import TrustDecision, TrustStoreError

_PACKAGE_SOURCE: ResourceSource = "package"
_GLOBAL_LAYERS: frozenset[ResourceSource] = frozenset({"global", "builtin"})


@dataclass(frozen=True, slots=True)
class ResourceLoadResult:
    descriptors: tuple[ResourceDescriptor, ...]
    extensions: tuple[ExtensionMetadata, ...]
    diagnostics: tuple[str, ...] = field(default_factory=tuple)


class DefaultResourceLoader:
    """First-wins composition across explicit/project/compat/package/global layers."""

    __slots__ = ("_extension_roots", "_package_roots", "_trust_store")

    def __init__(
        self,
        *,
        trust_store: object | None = None,
        package_roots: Mapping[ResourceKind, Sequence[Path]] | None = None,
        extension_roots: Sequence[Path] = (),
    ) -> None:
        self._trust_store = trust_store
        self._package_roots: dict[ResourceKind, tuple[Path, ...]] = {
            kind: tuple(roots) for kind, roots in (package_roots or {}).items()
        }
        self._extension_roots = tuple(extension_roots)

    def load(self, *, cwd: Path, agent_dir: Path) -> ResourceLoadResult:
        diagnostics: list[str] = []
        project_trusted = False
        if self._trust_store is not None:
            decision = _decision_of(self._trust_store, cwd)
            project_trusted = decision == TrustDecision.TRUSTED
            if not project_trusted:
                diagnostics.append(f"project resources under {cwd} skipped (untrusted)")
        descriptors = list(
            discover_resources(
                DiscoveryInputs(
                    cwd=cwd.resolve(),
                    agent_dir=agent_dir.resolve(),
                    project_trusted=project_trusted,
                )
            )
        )
        descriptors = _insert_package_layer(descriptors, self._collect_package_layer(diagnostics))
        extensions = _collect_extensions(self._extension_roots, diagnostics)
        return ResourceLoadResult(
            descriptors=tuple(descriptors),
            extensions=extensions,
            diagnostics=tuple(diagnostics),
        )

    def _collect_package_layer(self, diagnostics: list[str]) -> list[tuple[ResourceKind, Path]]:
        collected: list[tuple[ResourceKind, Path]] = []
        for kind, roots in self._package_roots.items():
            for root in roots:
                directory = root / kind if root.name != kind else root
                if not directory.is_dir():
                    diagnostics.append(f"package resource root missing: {root}")
                    continue
                for item in sorted(directory.iterdir()):
                    if item.is_file():
                        collected.append((kind, item))
                    elif (item / f"{kind}.md").is_file() or any(item.iterdir()):
                        for child in sorted(item.rglob("*")):
                            if child.is_file():
                                collected.append((kind, child))
        return collected


def _insert_package_layer(
    base: list[ResourceDescriptor],
    package_items: list[tuple[ResourceKind, Path]],
) -> list[ResourceDescriptor]:
    package_descriptors = [
        ResourceDescriptor(kind=kind, name=path.stem, path=path.resolve(), source=_PACKAGE_SOURCE)
        for kind, path in package_items
    ]
    insert_at = len(base)
    for index, descriptor in enumerate(base):
        if descriptor.source in _GLOBAL_LAYERS:
            insert_at = index
            break
    merged = list(base[:insert_at])
    seen = {(item.kind, item.name) for item in base[:insert_at]}
    for descriptor in package_descriptors:
        identity = (descriptor.kind, descriptor.name)
        if identity in seen:
            continue
        seen.add(identity)
        merged.append(descriptor)
    tail_seen = set(seen)
    for descriptor in base[insert_at:]:
        identity = (descriptor.kind, descriptor.name)
        if identity in tail_seen:
            continue
        tail_seen.add(identity)
        merged.append(descriptor)
    return merged


def _collect_extensions(
    roots: Sequence[Path], diagnostics: list[str]
) -> tuple[ExtensionMetadata, ...]:
    discovered: list[ExtensionMetadata] = []
    for root in roots:
        if not root.is_dir():
            diagnostics.append(f"extension root missing: {root}")
            continue
        discovered.extend(discover_extensions(root))
    return tuple(discovered)


def _decision_of(trust_store: object, cwd: Path) -> TrustDecision:
    try:
        return trust_store.get(cwd)  # type: ignore[attr-defined]
    except TrustStoreError as error:
        raise RuntimeError(f"trust store failure: {error}") from error


__all__ = ["DefaultResourceLoader", "ResourceLoadResult"]
