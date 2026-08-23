from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from pi_coding_agent.session.errors import SessionGraphError
from pi_coding_agent.session.fork import fork_session
from pi_coding_agent.session.models import SessionHeader, SessionInfoEntry
from pi_coding_agent.session.reader import read_session
from pi_coding_agent.session.writer import create_session_file

STAMP = "2026-08-24T00:00:00.000Z"


def _entry(entry_id: str, parent_id: str | None) -> SessionInfoEntry:
    return SessionInfoEntry(type="session_info", id=entry_id, parent_id=parent_id, timestamp=STAMP)


def test_fork_writes_selected_path_with_new_identity_and_cwd(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    source_header = SessionHeader(
        type="session", version=3, id="source", timestamp=STAMP, cwd="D:\\old"
    )
    create_session_file(
        source,
        (source_header, _entry("root", None), _entry("left", "root"), _entry("right", "root")),
    )
    source_hash = hashlib.sha256(source.read_bytes()).digest()
    target_cwd = tmp_path / "new-project"

    manager = fork_session(
        source,
        leaf_id="right",
        target_cwd=target_cwd,
        session_dir=tmp_path / "forks",
        session_id="forked",
        timestamp="2026-08-24T01:00:00.000Z",
    )

    assert manager.path is not None
    parsed = read_session(manager.path)
    assert parsed.header.id == "forked"
    assert parsed.header.cwd == str(target_cwd.resolve())
    assert parsed.header.parent_session == str(source.resolve())
    assert tuple(entry.id for entry in parsed.entries) == ("root", "right")
    assert hashlib.sha256(source.read_bytes()).digest() == source_hash


def test_fork_rejects_unknown_leaf_without_creating_output(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    create_session_file(
        source,
        (
            SessionHeader(type="session", version=3, id="source", timestamp=STAMP, cwd="x"),
            _entry("root", None),
        ),
    )
    target_dir = tmp_path / "forks"

    with pytest.raises(SessionGraphError, match="unknown entry"):
        fork_session(
            source,
            leaf_id="missing",
            target_cwd=tmp_path,
            session_dir=target_dir,
            session_id="forked",
            timestamp=STAMP,
        )

    assert not target_dir.exists()
