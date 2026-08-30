"""Open-or-create semantics and catalog cwd filtering (P11.5-T17)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pi_coding_agent.session.catalog import (
    list_sessions,
    open_or_create_session,
    open_session,
)
from pi_coding_agent.session.errors import SessionNotFoundError

_TIMESTAMP = "2026-08-30T00:00:00.000Z"
_SESSION_ID = "0123456789abcdef0123456789abcdef"


def _seed(session_dir: Path, cwd: Path, session_id: str = _SESSION_ID) -> Path:
    from pi_coding_agent.session.manager import SessionManager

    manager = SessionManager.create(
        cwd=cwd,
        session_dir=session_dir,
        session_id=session_id,
        timestamp=_TIMESTAMP,
    )
    from pi_coding_agent.session.models import MessageEntry

    manager.append(
        MessageEntry(
            type="message",
            id="e1",
            parent_id=None,
            timestamp="2026-08-30T00:00:01.000Z",
            message={
                "role": "assistant",
                "content": [{"type": "text", "text": "hi"}],
                "timestamp": 0,
                "stopReason": "stop",
                "api": "fake",
                "provider": "fake",
                "model": "fake-1",
                "usage": {
                    "input": 0,
                    "output": 0,
                    "cacheRead": 0,
                    "cacheWrite": 0,
                    "totalTokens": 0,
                    "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "total": 0},
                },
            },
        )
    )
    assert manager.path is not None
    return manager.path


def test_open_or_create_returns_existing_session(tmp_path: Path) -> None:
    _seed(tmp_path / "sessions", tmp_path)
    before = sorted(p.name for p in (tmp_path / "sessions").glob("*.jsonl"))
    manager = open_or_create_session(
        _SESSION_ID,
        session_dir=tmp_path / "sessions",
        cwd=tmp_path,
        timestamp_factory=lambda: _TIMESTAMP,
    )
    after = sorted(p.name for p in (tmp_path / "sessions").glob("*.jsonl"))
    assert manager.header.id == _SESSION_ID
    assert before == after


def test_open_or_create_creates_for_missing_valid_id(tmp_path: Path) -> None:
    manager = open_or_create_session(
        _SESSION_ID,
        session_dir=tmp_path / "sessions",
        cwd=tmp_path,
        timestamp_factory=lambda: _TIMESTAMP,
    )
    assert manager.header.id == _SESSION_ID
    assert manager.header.cwd == str(tmp_path.resolve())
    from pi_coding_agent.session.models import MessageEntry

    manager.append(
        MessageEntry(
            type="message",
            id="e1",
            parent_id=None,
            timestamp="2026-08-30T00:00:01.000Z",
            message={
                "role": "assistant",
                "content": [{"type": "text", "text": "hi"}],
                "timestamp": 0,
                "stopReason": "stop",
                "api": "fake",
                "provider": "fake",
                "model": "fake-1",
                "usage": {
                    "input": 0,
                    "output": 0,
                    "cacheRead": 0,
                    "cacheWrite": 0,
                    "totalTokens": 0,
                    "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "total": 0},
                },
            },
        )
    )
    created = list((tmp_path / "sessions").glob(f"*{_SESSION_ID}.jsonl"))
    assert len(created) == 1


def test_open_or_create_refuses_invalid_id(tmp_path: Path) -> None:
    from pi_coding_agent.session.errors import InvalidSessionIdError

    with pytest.raises(InvalidSessionIdError):
        open_or_create_session(
            "not a session id!",
            session_dir=tmp_path / "sessions",
            cwd=tmp_path,
            timestamp_factory=lambda: _TIMESTAMP,
        )


def test_open_or_create_keeps_path_semantics(tmp_path: Path) -> None:
    with pytest.raises(SessionNotFoundError):
        open_or_create_session(
            str(tmp_path / "missing.jsonl"),
            session_dir=tmp_path / "sessions",
            cwd=tmp_path,
            timestamp_factory=lambda: _TIMESTAMP,
        )


def test_open_or_create_refuses_when_id_exists_but_unreadable(tmp_path: Path) -> None:
    directory = tmp_path / "sessions"
    directory.mkdir()
    (directory / f"2026-08-30T00-00-00-000Z_{_SESSION_ID}.jsonl").write_bytes(
        b'{"type":"session","vers'
    )
    with pytest.raises(SessionNotFoundError):
        open_or_create_session(
            _SESSION_ID,
            session_dir=directory,
            cwd=tmp_path,
            timestamp_factory=lambda: _TIMESTAMP,
        )


def test_list_sessions_cwd_filter_ignores_drive_letter_case(tmp_path: Path) -> None:
    if sys.platform != "win32":
        pytest.skip("Windows drive-letter casing")
    session_dir = tmp_path / "sessions"
    path = _seed(session_dir, tmp_path)
    lowered_cwd = str(tmp_path.resolve())
    head, sep, tail = lowered_cwd.partition(":\\")
    if sep:
        lowered_cwd = f"{head.lower()}:{sep[1:]}{tail}"
    catalog = list_sessions(cwd=lowered_cwd, session_dir=session_dir)
    assert [s.path for s in catalog.sessions] == [path]


def test_list_sessions_resolves_relative_session_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _seed(tmp_path / "sessions", tmp_path)
    catalog = list_sessions(cwd=tmp_path, session_dir="sessions")
    assert len(catalog.sessions) == 1


def test_open_session_by_id_accepts_relative_session_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _seed(tmp_path / "sessions", tmp_path)
    manager = open_session(_SESSION_ID, session_dir="sessions")
    assert manager.header.id == _SESSION_ID
