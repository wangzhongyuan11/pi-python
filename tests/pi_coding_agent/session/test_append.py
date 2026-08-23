from __future__ import annotations

from pathlib import Path

import pytest

from pi_ai import JsonValue
from pi_coding_agent.session.errors import InvalidSessionIdError
from pi_coding_agent.session.manager import SessionManager
from pi_coding_agent.session.models import MessageEntry, SessionInfoEntry
from pi_coding_agent.session.reader import read_session


def _message(entry_id: str, parent_id: str | None, role: str) -> MessageEntry:
    message: dict[str, JsonValue] = {"role": role, "content": "hello", "timestamp": 1}
    if role == "assistant":
        message.update(
            {
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
            }
        )
    return MessageEntry(
        type="message",
        id=entry_id,
        parent_id=parent_id,
        timestamp=f"2026-08-24T00:00:0{entry_id[-1]}.000Z",
        message=message,
    )


def test_create_delays_file_until_first_assistant_message(tmp_path: Path) -> None:
    manager = SessionManager.create(
        cwd=tmp_path,
        session_dir=tmp_path / "sessions",
        session_id="session-1",
        timestamp="2026-08-24T00:00:00.000Z",
    )
    manager.append(_message("e1", None, "user"))

    assert manager.path is not None
    assert not manager.path.exists()

    manager.append(_message("e2", "e1", "assistant"))

    assert manager.path.exists()
    parsed = read_session(manager.path)
    assert [entry.id for entry in parsed.entries] == ["e1", "e2"]


def test_persisted_append_keeps_existing_bytes_as_exact_prefix(tmp_path: Path) -> None:
    manager = SessionManager.create(
        cwd=tmp_path,
        session_dir=tmp_path / "sessions",
        session_id="session-1",
        timestamp="2026-08-24T00:00:00.000Z",
    )
    manager.append(_message("e1", None, "assistant"))
    assert manager.path is not None
    before = manager.path.read_bytes()

    manager.append(
        SessionInfoEntry(
            type="session_info",
            id="e2",
            parent_id="e1",
            timestamp="2026-08-24T00:00:02.000Z",
            name="demo",
        )
    )

    assert manager.path.read_bytes().startswith(before)
    assert [entry.id for entry in read_session(manager.path).entries] == ["e1", "e2"]


def test_in_memory_manager_never_creates_a_file(tmp_path: Path) -> None:
    manager = SessionManager.in_memory(
        cwd=tmp_path,
        session_id="memory-1",
        timestamp="2026-08-24T00:00:00.000Z",
    )

    manager.append(_message("e1", None, "assistant"))

    assert manager.path is None
    assert manager.entries[-1].id == "e1"
    assert list(tmp_path.rglob("*.jsonl")) == []


def test_create_rejects_unsafe_session_id(tmp_path: Path) -> None:
    with pytest.raises(InvalidSessionIdError):
        SessionManager.create(
            cwd=tmp_path,
            session_dir=tmp_path,
            session_id="../escape",
            timestamp="2026-08-24T00:00:00.000Z",
        )


def test_failed_persisted_append_does_not_advance_memory_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = SessionManager.create(
        cwd=tmp_path, session_dir=tmp_path, session_id="s1", timestamp="2026-08-24T00:00:00.000Z"
    )
    manager.append(_message("e1", None, "assistant"))
    before = manager.entries

    def fail_append(*_args: object) -> None:
        raise OSError("injected append failure")

    monkeypatch.setattr("pi_coding_agent.session.manager.append_session_record", fail_append)

    with pytest.raises(OSError, match="injected"):
        manager.append(
            SessionInfoEntry(
                type="session_info",
                id="e2",
                parent_id="e1",
                timestamp="2026-08-24T00:00:02.000Z",
            )
        )

    assert manager.entries == before
    assert manager.leaf_id == "e1"
