from __future__ import annotations

import hashlib
from pathlib import Path

import pi_coding_agent
from pi_coding_agent.sdk import import_pi_session
from pi_coding_agent.session.models import MessageEntry, SessionHeader
from pi_coding_agent.session.writer import encode_record_line


def test_sdk_import_preserves_source_and_is_exported_from_package(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    source.write_bytes(
        b"".join(
            (
                encode_record_line(
                    SessionHeader(
                        type="session",
                        version=3,
                        id="import-sdk",
                        timestamp="2026-08-24T00:00:00.000Z",
                        cwd=str(tmp_path.resolve()),
                    )
                ),
                encode_record_line(
                    MessageEntry(
                        type="message",
                        id="assistant",
                        parent_id=None,
                        timestamp="2026-08-24T00:00:01.000Z",
                        message={
                            "role": "assistant",
                            "content": [],
                            "api": "fake",
                            "provider": "fake",
                            "model": "fake-1",
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
                ),
            )
        )
    )
    before = hashlib.sha256(source.read_bytes()).hexdigest()

    result = import_pi_session(source, session_dir=tmp_path / "sessions")

    assert result.session_id == "import-sdk"
    assert result.session_file.read_bytes() == source.read_bytes()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    assert pi_coding_agent.import_pi_session is import_pi_session
