"""Trailing torn-line session repair (P11.5-T16)."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

from pi_coding_agent.cli.main import main
from pi_coding_agent.session.reader import read_session
from pi_coding_agent.session.repair import repair_session

_HEADER = {
    "type": "session",
    "version": 3,
    "id": "0123456789abcdef0123456789abcdef",
    "timestamp": "2026-08-30T00:00:00.000Z",
    "cwd": "C:/tmp/proj",
}
_ENTRY = {
    "type": "message",
    "id": "e1",
    "parentId": None,
    "timestamp": "2026-08-30T00:00:01.000Z",
    "message": {"role": "user", "content": "hello", "timestamp": 0},
}


def _write(path: Path, *lines: bytes) -> bytes:
    payload = b"".join(line if line.endswith(b"\n") else line + b"\n" for line in lines)
    path.write_bytes(payload)
    return payload


def _header_line() -> bytes:
    return json.dumps(_HEADER).encode("utf-8")


def _entry_line() -> bytes:
    return json.dumps(_ENTRY).encode("utf-8")


def test_clean_file_refuses_repair_and_keeps_bytes(tmp_path: Path) -> None:
    path = tmp_path / "s.jsonl"
    payload = _write(path, _header_line(), _entry_line())
    result = repair_session(path)
    assert result.status == "clean"
    assert path.read_bytes() == payload


def test_torn_last_line_is_truncated_prefix_kept(tmp_path: Path) -> None:
    path = tmp_path / "s.jsonl"
    payload = _write(path, _header_line(), _entry_line())
    torn = b'{"type":"message","id":"e2","parentId":"e1"'
    path.write_bytes(payload + torn)
    result = repair_session(path)
    assert result.status == "truncated"
    repaired = path.read_bytes()
    assert repaired == payload
    parsed = read_session(path)
    assert parsed.entries[0].id == "e1"


def test_damage_before_last_line_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "s.jsonl"
    _write(
        path,
        _header_line(),
        b'{"type":"message","id":"e1"',  # torn in the middle
        _entry_line(),
    )
    payload = path.read_bytes()
    result = repair_session(path)
    assert result.status == "refused"
    assert path.read_bytes() == payload


def test_structural_corruption_in_last_line_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "s.jsonl"
    _write(path, _header_line(), _entry_line())
    path.write_bytes(path.read_bytes() + b'{"type":"message","id":"e2"}\n')  # valid JSON, bad entry
    before = path.read_bytes()
    result = repair_session(path)
    assert result.status == "refused"
    assert path.read_bytes() == before


def test_torn_header_alone_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "s.jsonl"
    path.write_bytes(b'{"type":"session","vers')
    result = repair_session(path)
    assert result.status == "refused"


def test_cli_session_repair_command_truncates(tmp_path: Path) -> None:
    path = tmp_path / "s.jsonl"
    payload = _write(path, _header_line(), _entry_line())
    path.write_bytes(payload + b'{"type":"mess')
    stdout, stderr = StringIO(), StringIO()
    code = main(
        ["session", "repair", str(path)],
        stdout=stdout,
        stderr=stderr,
        cwd=tmp_path,
        environ={},
    )
    assert code == 0
    assert "repaired" in stdout.getvalue()
    assert path.read_bytes() == payload


def test_cli_session_repair_reports_clean_file(tmp_path: Path) -> None:
    path = tmp_path / "s.jsonl"
    _write(path, _header_line(), _entry_line())
    stdout, stderr = StringIO(), StringIO()
    code = main(
        ["session", "repair", str(path)],
        stdout=stdout,
        stderr=stderr,
        cwd=tmp_path,
        environ={},
    )
    assert code == 0
    assert "no repair needed" in stdout.getvalue()


def test_cli_session_repair_fails_on_refused_file(tmp_path: Path) -> None:
    path = tmp_path / "s.jsonl"
    _write(path, _header_line(), b'{"type":"message","id":"e1"', _entry_line())
    stdout, stderr = StringIO(), StringIO()
    code = main(
        ["session", "repair", str(path)],
        stdout=stdout,
        stderr=stderr,
        cwd=tmp_path,
        environ={},
    )
    assert code == 1
