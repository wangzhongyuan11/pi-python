"""Trusted context-file discovery from root to the active working directory."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DEFAULT_CONTEXT_CANDIDATES = (
    "AGENTS.override.md",
    "AGENTS.md",
    "AGENTS.MD",
    "CLAUDE.md",
    "CLAUDE.MD",
)


@dataclass(frozen=True, slots=True, kw_only=True)
class ContextFile:
    path: Path
    content: str


def _load_first(directory: Path, candidates: tuple[str, ...]) -> ContextFile | None:
    for name in candidates:
        path = directory / name
        if path.is_file():
            return ContextFile(path=path.resolve(), content=path.read_text(encoding="utf-8"))
    return None


def _directories(root: Path, cwd: Path) -> tuple[Path, ...]:
    try:
        relative = cwd.relative_to(root)
    except ValueError as error:
        raise ValueError(f"context root {root} is not an ancestor of cwd {cwd}") from error
    result = [root]
    current = root
    for part in relative.parts:
        current /= part
        result.append(current)
    return tuple(result)


def load_context_files(
    *,
    cwd: Path,
    agent_dir: Path,
    project_trusted: bool,
    project_root: Path | None = None,
    candidates: tuple[str, ...] = DEFAULT_CONTEXT_CANDIDATES,
) -> tuple[ContextFile, ...]:
    resolved_cwd = cwd.resolve()
    result: list[ContextFile] = []
    global_context = _load_first(agent_dir.resolve(), candidates)
    if global_context is not None:
        result.append(global_context)
    if not project_trusted:
        return tuple(result)
    root = Path(resolved_cwd.anchor).resolve() if project_root is None else project_root.resolve()
    seen = {item.path for item in result}
    for directory in _directories(root, resolved_cwd):
        context = _load_first(directory, candidates)
        if context is not None and context.path not in seen:
            result.append(context)
            seen.add(context.path)
    return tuple(result)


__all__ = ["ContextFile", "DEFAULT_CONTEXT_CANDIDATES", "load_context_files"]
