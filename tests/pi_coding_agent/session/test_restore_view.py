from __future__ import annotations

from pathlib import Path

from pi_coding_agent.session.context import ModelSelection
from pi_coding_agent.session.models import (
    CompactionEntry,
    MessageEntry,
    SessionInfoEntry,
)
from pi_coding_agent.session.reader import read_session
from pi_coding_agent.session.restore import restore_session_state
from pi_coding_agent.session.tree import SessionTree
from pi_coding_agent.session.view import session_tree_view

STAMP = "2026-08-24T00:00:00.000Z"
FIXTURE = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "session_v3" / "canonical.jsonl"
)


def _fixture_tree() -> SessionTree:
    parsed = read_session(FIXTURE)
    return SessionTree.build(parsed.entries)


def test_restore_replays_fixture_model_thinking_and_compaction() -> None:
    tree = _fixture_tree()

    state = restore_session_state(tree, "e9")

    assert state.thinking_level == "high"
    assert state.model == ModelSelection(provider="deepseek", model_id="deepseek-chat")
    assert isinstance(state.compaction, CompactionEntry)
    assert state.compaction.id == "e7"
    assert state.compaction.first_kept_entry_id == "e1"


def test_restore_defaults_when_path_has_no_state_entries() -> None:
    manager_tree = SessionTree.build(
        (
            MessageEntry(
                type="message",
                id="m1",
                parent_id=None,
                timestamp=STAMP,
                message={"role": "user", "content": [], "timestamp": 1},
            ),
        )
    )

    state = restore_session_state(manager_tree, "m1")

    assert state.thinking_level == "off"
    assert state.model is None
    assert state.compaction is None


def test_restore_prefers_assistant_message_over_earlier_model_change() -> None:
    tree = SessionTree.build(
        (
            MessageEntry(
                type="message",
                id="m1",
                parent_id=None,
                timestamp=STAMP,
                message={"role": "user", "content": [], "timestamp": 1},
            ),
            MessageEntry(
                type="message",
                id="m2",
                parent_id="m1",
                timestamp=STAMP,
                message={
                    "role": "assistant",
                    "content": [],
                    "api": "test",
                    "provider": "deepseek",
                    "model": "deepseek-reasoner",
                    "usage": {},
                    "stopReason": "stop",
                    "timestamp": 2,
                },
            ),
        )
    )

    state = restore_session_state(tree, "m2")

    assert state.model == ModelSelection(provider="deepseek", model_id="deepseek-reasoner")


def test_view_resolves_labels_and_append_order_children() -> None:
    tree = _fixture_tree()

    roots = session_tree_view(tree)

    assert [node.entry.id for node in roots] == ["e1"]
    first = roots[0]
    assert first.label == "root"
    assert first.label_timestamp == "2026-08-24T00:00:08.000Z"
    child_ids = [child.entry.id for child in first.children]
    assert child_ids == ["e2"]
    labeled = [node for node in roots[0].children]
    assert all(node.label is None for node in labeled)


def test_view_lists_later_siblings_in_append_order() -> None:
    tree = SessionTree.build(
        (
            SessionInfoEntry(type="session_info", id="root", parent_id=None, timestamp=STAMP),
            SessionInfoEntry(type="session_info", id="left", parent_id="root", timestamp=STAMP),
            SessionInfoEntry(type="session_info", id="right", parent_id="root", timestamp=STAMP),
        )
    )

    roots = session_tree_view(tree)

    assert [node.entry.id for node in roots] == ["root"]
    assert [child.entry.id for child in roots[0].children] == ["left", "right"]
