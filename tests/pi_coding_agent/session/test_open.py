from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from pi_coding_agent.session.catalog import open_session
from pi_coding_agent.session.errors import SessionNotFoundError
from pi_coding_agent.session.models import SessionHeader, SessionInfoEntry
from pi_coding_agent.session.writer import create_session_file

STAMP = "2026-08-24T00:00:00.000Z"


def _make(path: Path, session_id: str = "session-full") -> None:
    create_session_file(
        path,
        (
            SessionHeader(
                type="session", version=3, id=session_id, timestamp=STAMP, cwd="D:\\work"
            ),
            SessionInfoEntry(
                type="session_info",
                id="e1",
                parent_id=None,
                timestamp=STAMP,
                name="demo",
            ),
        ),
    )


def test_open_exact_path_is_strict_and_read_only(tmp_path: Path) -> None:
    path = tmp_path / "session.jsonl"
    _make(path)
    before_hash = hashlib.sha256(path.read_bytes()).digest()
    before_mtime = path.stat().st_mtime_ns

    manager = open_session(path)

    assert manager.header.id == "session-full"
    assert manager.leaf_id == "e1"
    assert hashlib.sha256(path.read_bytes()).digest() == before_hash
    assert path.stat().st_mtime_ns == before_mtime


def test_open_resolves_only_a_complete_session_id(tmp_path: Path) -> None:
    path = tmp_path / "2026_session-full.jsonl"
    _make(path)

    assert open_session("session-full", session_dir=tmp_path).path == path.resolve()
    with pytest.raises(SessionNotFoundError):
        open_session("session", session_dir=tmp_path)


def test_open_rejects_missing_path(tmp_path: Path) -> None:
    with pytest.raises(SessionNotFoundError):
        open_session(tmp_path / "missing.jsonl")
