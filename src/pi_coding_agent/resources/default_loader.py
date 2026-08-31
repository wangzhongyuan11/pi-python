"""Compose discovery, trust, packages, and extensions into one loader."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from ..extensions.loader import discover_extensions
from ..extensions.metadata import (
    MANIFEST_NAME,
    ExtensionManifestError,
    ExtensionMetadata,
    read_manifest,
)
from ..ports import ResourceDescriptor, ResourceKind, ResourceRoot, ResourceSource
from ..prompts.system import build_system_prompt, discover_prompt_files
from .context_files import load_context_files
from .discovery import DiscoveryInputs, discover_resources
from .skills import format_skills_for_prompt, load_skill_descriptors
from .trust import TrustDecision, TrustStoreError

_PACKAGE_SOURCE: ResourceSource = "package"
_GLOBAL_LAYERS: frozenset[ResourceSource] = frozenset({"global", "builtin"})


class _TrustReader(Protocol):
    def get(self, cwd: Path) -> TrustDecision: ...


@dataclass(frozen=True, slots=True)
class ResourceLoadResult:
    descriptors: tuple[ResourceDescriptor, ...]
    extensions: tuple[ExtensionMetadata, ...]
    diagnostics: tuple[str, ...] = field(default_factory=tuple)
    project_trusted: bool = False


class DefaultResourceLoader:
    """First-wins composition across explicit/project/compat/package/global layers."""

    __slots__ = (
        "_agent_dir",
        "_extension_roots",
        "_last_cwd",
        "_last_result",
        "_package_roots",
        "_project_trust_overrides",
        "_resource_roots",
        "_trust_store",
    )

    def __init__(
        self,
        *,
        trust_store: _TrustReader | None = None,
        package_roots: Mapping[ResourceKind, Sequence[Path]] | None = None,
        extension_roots: Sequence[Path] = (),
        resource_roots: Sequence[ResourceRoot] = (),
        agent_dir: Path | None = None,
    ) -> None:
        self._trust_store = trust_store
        legacy_package_roots = tuple(
            ResourceRoot(kind=kind, path=root, source="package")
            for kind, roots in (package_roots or {}).items()
            for root in roots
        )
        legacy_extension_roots = tuple(
            ResourceRoot(kind="extension", path=root, source="explicit") for root in extension_roots
        )
        self._resource_roots = _resolve_roots(
            (*resource_roots, *legacy_package_roots, *legacy_extension_roots)
        )
        self._package_roots: dict[ResourceKind, tuple[Path, ...]] = {}
        self._extension_roots: tuple[Path, ...] = ()
        self._index_roots()
        self._agent_dir = (agent_dir or _default_agent_dir()).expanduser().resolve()
        self._project_trust_overrides: dict[Path, bool] = {}
        self._last_cwd: Path | None = None
        self._last_result: ResourceLoadResult | None = None

    @property
    def agent_dir(self) -> Path:
        return self._agent_dir

    @property
    def last_result(self) -> ResourceLoadResult:
        if self._last_result is None:
            raise RuntimeError("resources have not been discovered yet")
        return self._last_result

    @property
    def resolved_roots(self) -> tuple[ResourceRoot, ...]:
        return self._resource_roots

    def discover(self, cwd: Path) -> tuple[ResourceDescriptor, ...]:
        return self.load(cwd=cwd, agent_dir=self._agent_dir).descriptors

    def set_project_trusted(self, cwd: Path, trusted: bool) -> None:
        """Set the resolved trust decision for one runtime cwd."""
        self._project_trust_overrides[cwd.resolve()] = trusted

    def set_resource_roots(self, roots: Sequence[ResourceRoot]) -> None:
        self._resource_roots = _resolve_roots(roots)
        self._index_roots()

    def source_for(self, kind: ResourceKind, path: Path) -> ResourceSource:
        resolved = path.resolve()
        for root in self._resource_roots:
            if root.kind == kind and (resolved == root.path or resolved.is_relative_to(root.path)):
                return root.source
        if resolved.is_relative_to(self._agent_dir / f"{kind}s"):
            return "global"
        return "project"

    def load(self, *, cwd: Path, agent_dir: Path) -> ResourceLoadResult:
        diagnostics: list[str] = []
        resolved_cwd = cwd.resolve()
        project_trusted = self._project_trust_overrides.get(resolved_cwd, False)
        if resolved_cwd not in self._project_trust_overrides and self._trust_store is not None:
            decision = _decision_of(self._trust_store, cwd)
            project_trusted = decision == TrustDecision.TRUSTED
        if not project_trusted:
            diagnostics.append(f"project resources under {cwd} skipped (untrusted)")
        descriptors = list(
            discover_resources(
                DiscoveryInputs(
                    cwd=resolved_cwd,
                    agent_dir=agent_dir.resolve(),
                    project_trusted=project_trusted,
                    explicit=self._explicit_paths(),
                )
            )
        )
        descriptors = _insert_package_layer(descriptors, self._collect_package_layer(diagnostics))
        extension_roots = [*self._extension_roots, agent_dir / "extensions"]
        if project_trusted:
            extension_roots.append(cwd / ".pi-python" / "extensions")
        extensions = _collect_extensions(extension_roots, diagnostics)
        result = ResourceLoadResult(
            descriptors=tuple(descriptors),
            extensions=extensions,
            diagnostics=tuple(diagnostics),
            project_trusted=project_trusted,
        )
        self._last_cwd = resolved_cwd
        self._last_result = result
        return result

    def build_system_prompt(self, cwd: Path) -> str:
        resolved_cwd = cwd.resolve()
        result = (
            self._last_result
            if self._last_result is not None and self._last_cwd == resolved_cwd
            else self.load(cwd=resolved_cwd, agent_dir=self._agent_dir)
        )
        prompt_files = discover_prompt_files(
            cwd=resolved_cwd,
            agent_dir=self._agent_dir,
            project_trusted=result.project_trusted,
        )
        context_files = load_context_files(
            cwd=resolved_cwd,
            agent_dir=self._agent_dir,
            project_trusted=result.project_trusted,
            project_root=_project_root(resolved_cwd),
        )
        skill_paths = tuple(
            descriptor.path
            for descriptor in result.descriptors
            if descriptor.kind == "skill" and descriptor.path is not None
        )
        skills = format_skills_for_prompt(load_skill_descriptors(skill_paths).skills)
        append_parts = tuple(part for part in (prompt_files.append_system_prompt, skills) if part)
        return build_system_prompt(
            cwd=resolved_cwd,
            system_prompt=prompt_files.system_prompt,
            append_system_prompt="\n\n".join(append_parts) or None,
            context_files=context_files,
        )

    def _index_roots(self) -> None:
        package_roots: dict[ResourceKind, list[Path]] = {}
        extension_roots: list[Path] = []
        for root in self._resource_roots:
            if root.source == "package":
                package_roots.setdefault(root.kind, []).append(root.path)
            if root.kind == "extension":
                extension_roots.append(root.path)
        self._package_roots = {kind: tuple(paths) for kind, paths in package_roots.items()}
        self._extension_roots = tuple(extension_roots)

    def _explicit_paths(self) -> dict[ResourceKind, tuple[Path, ...]]:
        paths: dict[ResourceKind, list[Path]] = {}
        for root in self._resource_roots:
            if root.source != "explicit" or root.kind == "extension":
                continue
            paths.setdefault(root.kind, []).extend(_resource_files(root.path, root.kind))
        return {kind: tuple(items) for kind, items in paths.items()}

    def _collect_package_layer(self, diagnostics: list[str]) -> list[tuple[ResourceKind, Path]]:
        collected: list[tuple[ResourceKind, Path]] = []
        for kind, roots in self._package_roots.items():
            if kind == "extension":
                continue
            for root in roots:
                directory = root / kind if root.name not in {kind, f"{kind}s"} else root
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


def _project_root(cwd: Path) -> Path:
    for candidate in (cwd, *cwd.parents):
        if (candidate / ".git").exists():
            return candidate
    return cwd


def _collect_extensions(
    roots: Sequence[Path], diagnostics: list[str]
) -> tuple[ExtensionMetadata, ...]:
    discovered: list[ExtensionMetadata] = []
    seen: set[Path] = set()
    for root in roots:
        resolved = root.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if not root.is_dir():
            continue
        if (root / MANIFEST_NAME).is_file():
            try:
                discovered.append(read_manifest(root))
            except ExtensionManifestError:
                pass
            continue
        discovered.extend(discover_extensions(root))
    return tuple(discovered)


def _resolve_roots(roots: Sequence[ResourceRoot]) -> tuple[ResourceRoot, ...]:
    resolved: list[ResourceRoot] = []
    seen: set[tuple[ResourceKind, Path, str]] = set()
    for root in roots:
        item = ResourceRoot(
            kind=root.kind,
            path=root.path.expanduser().resolve(),
            source=root.source,
        )
        identity = (item.kind, item.path, item.source)
        if identity in seen:
            continue
        seen.add(identity)
        resolved.append(item)
    return tuple(resolved)


def _resource_files(root: Path, kind: ResourceKind) -> tuple[Path, ...]:
    if root.is_file():
        return (root,)
    if not root.is_dir():
        return ()
    if kind == "skill" and (root / "SKILL.md").is_file():
        return (root / "SKILL.md",)
    files = [item for item in root.iterdir() if item.is_file()]
    if kind == "skill":
        files.extend(item / "SKILL.md" for item in root.iterdir() if (item / "SKILL.md").is_file())
    return tuple(sorted(files))


def _default_agent_dir() -> Path:
    configured = os.environ.get("PI_PYTHON_AGENT_DIR")
    return Path(configured) if configured else Path.home() / ".pi-python" / "agent"


def _decision_of(trust_store: _TrustReader, cwd: Path) -> TrustDecision:
    try:
        return trust_store.get(cwd)
    except TrustStoreError as error:
        raise RuntimeError(f"trust store failure: {error}") from error


__all__ = ["DefaultResourceLoader", "ResourceLoadResult"]
