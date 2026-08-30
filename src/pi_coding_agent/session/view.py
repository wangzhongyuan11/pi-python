"""Defensive tree view over a Session entry tree for selectors and UI."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from .errors import SessionGraphError
from .models import LabelEntry, SessionEntry
from .tree import SessionTree


@dataclass(frozen=True, slots=True)
class SessionTreeNode:
    entry: SessionEntry
    children: tuple[SessionTreeNode, ...]
    label: str | None = None
    label_timestamp: str | None = None


def _timestamp(value: str) -> float:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise SessionGraphError(f"invalid entry timestamp: {value}") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.timestamp()


def session_tree_view(tree: SessionTree) -> tuple[SessionTreeNode, ...]:
    labels: dict[str, LabelEntry] = {}
    for entry in tree.entries:
        if isinstance(entry, LabelEntry):
            labels[entry.target_id] = entry

    nodes: dict[str, SessionTreeNode] = {}
    for entry in reversed(tree.entries):
        label_entry = labels.get(entry.id)
        child_ids = sorted(
            tree.child_ids[entry.id],
            key=lambda child_id: _timestamp(tree.by_id[child_id].timestamp),
        )
        nodes[entry.id] = SessionTreeNode(
            entry=entry,
            children=tuple(nodes[child_id] for child_id in child_ids),
            label=label_entry.label if label_entry is not None else None,
            label_timestamp=label_entry.timestamp if label_entry is not None else None,
        )

    if tree.root_id is None:
        return ()
    return (nodes[tree.root_id],)


__all__ = ["SessionTreeNode", "session_tree_view"]
