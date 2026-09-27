"""Historical defect regression: JSONL trailing line without a newline."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from pi_coding_agent.session.catalog import open_session
from pi_coding_agent.session.models import SessionInfoEntry
from pi_coding_agent.session.reader import read_session


def _session_bytes() -> bytes:
    header = {
        "type": "session",
        "version": 3,
        "id": "regression00000000000000000000000aa",
        "timestamp": "2026-09-01T00:00:00.000Z",
        "cwd": "/regression/project",
    }
    user = {
        "type": "message",
        "id": "e001",
        "parentId": None,
        "timestamp": "2026-09-01T00:00:01.000Z",
        "message": {"role": "user", "content": "trailing line", "timestamp": 0},
    }
    return "\n".join((json.dumps(header), json.dumps(user))).encode("utf-8")  # no trailing newline


def test_reader_accepts_a_complete_final_line_without_trailing_newline(
    tmp_path: Path,
) -> None:
    path = tmp_path / "torn-free.jsonl"
    path.write_bytes(_session_bytes())

    parsed = read_session(path)
    assert [entry.id for entry in parsed.entries] == ["e001"]

    # Appending after a newline-less file keeps the session well-formed.
    manager = open_session(path)
    manager.append_session_info(
        "recovered",
        entry_id_factory=lambda: uuid4().hex,
        timestamp_factory=lambda: "2026-09-01T00:00:02.000Z",
    )
    reread = read_session(path)
    assert path.read_bytes().endswith(b"\n")
    assert len(reread.entries) == 2
    assert isinstance(reread.entries[-1], SessionInfoEntry)
    assert reread.entries[-1].name == "recovered"
