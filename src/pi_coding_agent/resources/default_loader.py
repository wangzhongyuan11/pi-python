"""Compose discovery, trust, packages, and extensions into one loader."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from ..extensions.loader import discover_extensions
from ..extensions.metadata import ExtensionMetadata
from ..ports import ResourceDescriptor, ResourceKind
from ..prompts.system import build_system_prompt, discover_prompt_files
from .context_files import load_context_files
from .descriptors import ResourceSource  # re-exported type value guard
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
        "_trust_store",
    )

    def __init__(
        self,
        *,
        trust_store: _TrustReader | None = None,
        package_roots: Mapping[ResourceKind, Sequence[Path]] | None = None,
        extension_roots: Sequence[Path] = (),
        agent_dir: Path | None = None,
    ) -> None:
        self._trust_store = trust_store
        self._package_roots: dict[ResourceKind, tuple[Path, ...]] = {
            kind: tuple(roots) for kind, roots in (package_roots or {}).items()
        }
        self._extension_roots = tuple(extension_roots)
        self._agent_dir = (agent_dir or _default_agent_dir()).expanduser().resolve()
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

    def discover(self, cwd: Path) -> tuple[ResourceDescriptor, ...]:
        return self.load(cwd=cwd, agent_dir=self._agent_dir).descriptors

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
        self._last_cwd = cwd.resolve()
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
        discovered.extend(discover_extensions(root))
    return tuple(discovered)


def _default_agent_dir() -> Path:
    configured = os.environ.get("PI_PYTHON_AGENT_DIR")
    return Path(configured) if configured else Path.home() / ".pi-python" / "agent"


def _decision_of(trust_store: _TrustReader, cwd: Path) -> TrustDecision:
    try:
        return trust_store.get(cwd)
    except TrustStoreError as error:
        raise RuntimeError(f"trust store failure: {error}") from error


__all__ = ["DefaultResourceLoader", "ResourceLoadResult"]
