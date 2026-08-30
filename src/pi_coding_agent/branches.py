"""Diff two branch paths of a Session tree without touching storage."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .session.models import SessionEntry


@dataclass(frozen=True, slots=True)
class BranchPathDiff:
    lca_id: str | None
    from_entries: tuple[SessionEntry, ...]
    to_entries: tuple[SessionEntry, ...]


def diff_branch_paths(
    from_path: Sequence[SessionEntry], to_path: Sequence[SessionEntry]
) -> BranchPathDiff:
    if not from_path:
        return BranchPathDiff(lca_id=None, from_entries=(), to_entries=())
    from_ids = {entry.id for entry in from_path}
    lca_id = next((entry.id for entry in reversed(to_path) if entry.id in from_ids), None)
    if lca_id is None:
        return BranchPathDiff(lca_id=None, from_entries=tuple(from_path), to_entries=tuple(to_path))
    from_index = next(index for index, entry in enumerate(from_path) if entry.id == lca_id)
    to_index = next(index for index, entry in enumerate(to_path) if entry.id == lca_id)
    return BranchPathDiff(
        lca_id=lca_id,
        from_entries=tuple(from_path[from_index + 1 :]),
        to_entries=tuple(to_path[to_index + 1 :]),
    )


__all__ = ["BranchPathDiff", "diff_branch_paths"]
