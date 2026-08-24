"""Defensive tree view over a Session entry tree for selectors and UI."""

from __future__ import annotations

from dataclasses import dataclass

from .models import LabelEntry, SessionEntry
from .tree import SessionTree


@dataclass(frozen=True, slots=True)
class SessionTreeNode:
    entry: SessionEntry
    children: tuple[SessionTreeNode, ...]
    label: str | None = None
    label_timestamp: str | None = None


def session_tree_view(tree: SessionTree) -> tuple[SessionTreeNode, ...]:
    labels: dict[str, LabelEntry] = {}
    for entry in tree.entries:
        if isinstance(entry, LabelEntry):
            labels[entry.target_id] = entry

    def build(entry: SessionEntry) -> SessionTreeNode:
        label_entry = labels.get(entry.id)
        return SessionTreeNode(
            entry=entry,
            children=tuple(build(child) for child in tree.children_of(entry.id)),
            label=label_entry.label if label_entry is not None else None,
            label_timestamp=label_entry.timestamp if label_entry is not None else None,
        )

    if tree.root_id is None:
        return ()
    return (build(tree.by_id[tree.root_id]),)


__all__ = ["SessionTreeNode", "session_tree_view"]
