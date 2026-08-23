from __future__ import annotations

import pytest

from pi_coding_agent.session.errors import SessionGraphError
from pi_coding_agent.session.models import SessionInfoEntry
from pi_coding_agent.session.tree import SessionTree


def _entry(entry_id: str, parent_id: str | None) -> SessionInfoEntry:
    return SessionInfoEntry(
        type="session_info",
        id=entry_id,
        parent_id=parent_id,
        timestamp="2026-08-24T00:00:00.000Z",
    )


def test_tree_indexes_children_leaves_and_active_path() -> None:
    tree = SessionTree.build(
        (_entry("root", None), _entry("left", "root"), _entry("right", "root"))
    )

    assert tree.root_id == "root"
    assert tree.leaf_ids == ("left", "right")
    assert tuple(item.id for item in tree.children_of("root")) == ("left", "right")
    assert tuple(item.id for item in tree.active_path("right")) == ("root", "right")


@pytest.mark.parametrize(
    "entries",
    [
        (_entry("same", None), _entry("same", "same")),
        (_entry("root", None), _entry("orphan", "missing")),
        (_entry("child", "parent"), _entry("parent", None)),
        (_entry("one", None), _entry("two", None)),
    ],
)
def test_tree_rejects_invalid_graphs(entries: tuple[SessionInfoEntry, ...]) -> None:
    with pytest.raises(SessionGraphError):
        SessionTree.build(entries)


def test_active_path_rejects_unknown_leaf() -> None:
    tree = SessionTree.build((_entry("root", None),))

    with pytest.raises(SessionGraphError, match="unknown entry"):
        tree.active_path("missing")
