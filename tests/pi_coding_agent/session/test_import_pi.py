from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from pi_coding_agent.session.errors import SessionImportError
from pi_coding_agent.session.importer import import_pi_session


def _source(path: Path, *, version: int = 3) -> bytes:
    records = [
        {
            "type": "session",
            "version": version,
            "id": "source-id",
            "timestamp": "2026-08-24T00:00:00.000Z",
            "cwd": "D:\\project",
            "futureHeader": {"keep": True},
        },
        {
            "type": "custom",
            "id": "e1",
            "parentId": None,
            "timestamp": "2026-08-24T00:00:01.000Z",
            "customType": "demo",
            "data": {"hello": "世界"},
            "futureEntry": 42,
        },
    ]
    data = b"".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
        for record in records
    )
    path.write_bytes(data)
    return data


def test_import_copies_valid_v3_bytes_and_returns_absolute_result(tmp_path: Path) -> None:
    source = tmp_path / "upstream.jsonl"
    original = _source(source)
    source_hash = hashlib.sha256(original).digest()

    result = import_pi_session(source, session_dir=tmp_path / "python-sessions")

    assert result.session_id == "source-id"
    assert result.source_file == source.resolve()
    assert result.session_file.is_absolute()
    assert result.session_file.read_bytes() == original
    assert hashlib.sha256(source.read_bytes()).digest() == source_hash


def test_import_rejects_old_versions_without_writing_output(tmp_path: Path) -> None:
    source = tmp_path / "v2.jsonl"
    _source(source, version=2)
    target = tmp_path / "target"

    with pytest.raises(SessionImportError, match="version 3"):
        import_pi_session(source, session_dir=target)

    assert not target.exists()


def test_import_never_overwrites_existing_target(tmp_path: Path) -> None:
    source = tmp_path / "upstream.jsonl"
    _source(source)
    target = tmp_path / "target"
    first = import_pi_session(source, session_dir=target)
    before = first.session_file.read_bytes()

    with pytest.raises(FileExistsError):
        import_pi_session(source, session_dir=target)

    assert first.session_file.read_bytes() == before
