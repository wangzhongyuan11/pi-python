from __future__ import annotations

from pi_coding_agent.branches import diff_branch_paths
from pi_coding_agent.session.models import SessionInfoEntry

STAMP = "2026-08-24T00:00:00.000Z"


def _entry(entry_id: str, parent_id: str | None) -> SessionInfoEntry:
    return SessionInfoEntry(type="session_info", id=entry_id, parent_id=parent_id, timestamp=STAMP)


def test_diverged_paths_share_the_deepest_ancestor_only() -> None:
    from_path = (_entry("root", None), _entry("a", "root"), _entry("b", "a"))
    to_path = (_entry("root", None), _entry("a", "root"), _entry("c", "a"))

    diff = diff_branch_paths(from_path, to_path)

    assert diff.lca_id == "a"
    assert tuple(item.id for item in diff.from_entries) == ("b",)
    assert tuple(item.id for item in diff.to_entries) == ("c",)


def test_branch_from_root_leaves_the_root_as_ancestor() -> None:
    from_path = (_entry("root", None),)
    to_path = (_entry("root", None), _entry("next", "root"))

    diff = diff_branch_paths(from_path, to_path)

    assert diff.lca_id == "root"
    assert diff.from_entries == ()
    assert tuple(item.id for item in diff.to_entries) == ("next",)


def test_identical_paths_produce_an_empty_diff_at_the_leaf() -> None:
    path = (_entry("root", None), _entry("a", "root"))

    diff = diff_branch_paths(path, path)

    assert diff.lca_id == "a"
    assert diff.from_entries == ()
    assert diff.to_entries == ()


def test_disjoint_paths_have_no_common_ancestor() -> None:
    from_path = (_entry("left", None), _entry("left-child", "left"))
    to_path = (_entry("right", None),)

    diff = diff_branch_paths(from_path, to_path)

    assert diff.lca_id is None
    assert tuple(item.id for item in diff.from_entries) == ("left", "left-child")
    assert tuple(item.id for item in diff.to_entries) == ("right",)


def test_missing_previous_position_has_nothing_to_diff() -> None:
    diff = diff_branch_paths((), (_entry("root", None),))

    assert diff.lca_id is None
    assert diff.from_entries == ()
    assert diff.to_entries == ()
