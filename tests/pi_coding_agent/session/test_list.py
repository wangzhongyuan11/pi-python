from __future__ import annotations

import os
from pathlib import Path

from pi_coding_agent.session.catalog import list_sessions
from pi_coding_agent.session.models import SessionHeader, SessionInfoEntry
from pi_coding_agent.session.writer import create_session_file

STAMP = "2026-08-24T00:00:00.000Z"


def _make(path: Path, session_id: str, cwd: Path, name: str) -> None:
    create_session_file(
        path,
        (
            SessionHeader(
                type="session",
                version=3,
                id=session_id,
                timestamp=STAMP,
                cwd=str(cwd.resolve()),
            ),
            SessionInfoEntry(
                type="session_info",
                id=f"{session_id}-entry",
                parent_id=None,
                timestamp=STAMP,
                name=name,
            ),
        ),
    )


def test_list_sorts_valid_sessions_and_isolates_corruption(tmp_path: Path) -> None:
    directory = tmp_path / "sessions"
    directory.mkdir()
    older = directory / "older.jsonl"
    newer = directory / "newer.jsonl"
    broken = directory / "broken.jsonl"
    _make(older, "older", tmp_path, "Old")
    _make(newer, "newer", tmp_path, "New")
    broken.write_text("not-json\n", encoding="utf-8")
    os.utime(older, ns=(1_000_000_000, 1_000_000_000))
    os.utime(newer, ns=(2_000_000_000, 2_000_000_000))
    mtimes = {path: path.stat().st_mtime_ns for path in (older, newer, broken)}

    result = list_sessions(cwd=tmp_path, session_dir=directory)

    assert [session.id for session in result.sessions] == ["newer", "older"]
    assert result.sessions[0].name == "New"
    assert [diagnostic.path for diagnostic in result.diagnostics] == [broken.resolve()]
    assert {path: path.stat().st_mtime_ns for path in mtimes} == mtimes


def test_list_filters_sessions_from_a_different_cwd(tmp_path: Path) -> None:
    directory = tmp_path / "sessions"
    directory.mkdir()
    _make(directory / "other.jsonl", "other", tmp_path / "other", "Other")

    result = list_sessions(cwd=tmp_path, session_dir=directory)

    assert result.sessions == ()
    assert result.diagnostics == ()
