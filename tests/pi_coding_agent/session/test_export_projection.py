from __future__ import annotations

import hashlib
from pathlib import Path

from pi_ai import UserMessage
from pi_coding_agent.session.export import export_session
from pi_coding_agent.session.models import MessageEntry, SessionHeader, SessionInfoEntry
from pi_coding_agent.session.writer import create_session_file

STAMP = "2026-08-24T00:00:00.000Z"


def test_export_returns_active_structured_projection_without_mutation(tmp_path: Path) -> None:
    path = tmp_path / "session.jsonl"
    create_session_file(
        path,
        (
            SessionHeader(type="session", version=3, id="s1", timestamp=STAMP, cwd=str(tmp_path)),
            MessageEntry(
                type="message",
                id="root",
                parent_id=None,
                timestamp=STAMP,
                message={"role": "user", "content": "root", "timestamp": 1},
            ),
            SessionInfoEntry(
                type="session_info",
                id="left",
                parent_id="root",
                timestamp=STAMP,
                name="left",
            ),
            MessageEntry(
                type="message",
                id="right",
                parent_id="root",
                timestamp=STAMP,
                message={"role": "user", "content": "right", "timestamp": 2},
            ),
        ),
    )
    original_hash = hashlib.sha256(path.read_bytes()).digest()

    transcript = export_session(path, leaf_id="right")

    assert transcript.session_id == "s1"
    assert transcript.leaf_id == "right"
    assert tuple(entry.id for entry in transcript.entries) == ("root", "right")
    user_content = [
        message.content
        for message in transcript.context.messages
        if isinstance(message, UserMessage)
    ]
    assert user_content == [
        "root",
        "right",
    ]
    assert hashlib.sha256(path.read_bytes()).digest() == original_hash
