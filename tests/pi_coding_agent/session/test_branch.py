from __future__ import annotations

from pathlib import Path

import pytest

from pi_coding_agent.session.errors import SessionGraphError
from pi_coding_agent.session.manager import SessionManager
from pi_coding_agent.session.models import SessionInfoEntry

STAMP = "2026-08-24T00:00:00.000Z"


def _entry(entry_id: str, parent_id: str | None) -> SessionInfoEntry:
    return SessionInfoEntry(type="session_info", id=entry_id, parent_id=parent_id, timestamp=STAMP)


def test_branch_moves_only_leaf_and_next_append_creates_a_child(tmp_path: Path) -> None:
    manager = SessionManager.in_memory(cwd=tmp_path, session_id="s1", timestamp=STAMP)
    manager.append(_entry("root", None))
    manager.append(_entry("old", "root"))

    manager.branch("root")
    manager.append(_entry("new", "root"))

    assert manager.leaf_id == "new"
    assert tuple(item.id for item in manager.active_path()) == ("root", "new")
    assert tuple(item.id for item in manager.entries) == ("root", "old", "new")


def test_branch_does_not_rewrite_persisted_history(tmp_path: Path) -> None:
    manager = SessionManager.create(
        cwd=tmp_path, session_dir=tmp_path, session_id="s1", timestamp=STAMP
    )
    from pi_coding_agent.session.models import MessageEntry

    manager.append(
        MessageEntry(
            type="message",
            id="root",
            parent_id=None,
            timestamp=STAMP,
            message={
                "role": "assistant",
                "content": [],
                "api": "test",
                "provider": "test",
                "model": "test-model",
                "usage": {
                    "input": 0,
                    "output": 0,
                    "cacheRead": 0,
                    "cacheWrite": 0,
                    "totalTokens": 0,
                    "cost": {
                        "input": 0.0,
                        "output": 0.0,
                        "cacheRead": 0.0,
                        "cacheWrite": 0.0,
                        "total": 0.0,
                    },
                },
                "stopReason": "stop",
                "timestamp": 1,
            },
        )
    )
    assert manager.path is not None
    original = manager.path.read_bytes()

    manager.branch("root")

    assert manager.path.read_bytes() == original


def test_branch_rejects_unknown_target_without_state_change(tmp_path: Path) -> None:
    manager = SessionManager.in_memory(cwd=tmp_path, session_id="s1", timestamp=STAMP)
    manager.append(_entry("root", None))

    with pytest.raises(SessionGraphError, match="unknown entry"):
        manager.branch("missing")

    assert manager.leaf_id == "root"
