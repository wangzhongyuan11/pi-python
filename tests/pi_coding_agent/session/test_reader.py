from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from pi_coding_agent.session.errors import SessionCorruptError
from pi_coding_agent.session.reader import read_session


def _write(path: Path, records: list[dict[str, object]]) -> bytes:
    data = b"".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"
        for record in records
    )
    path.write_bytes(data)
    return data


def _header() -> dict[str, object]:
    return {
        "type": "session",
        "version": 3,
        "id": "s1",
        "timestamp": "2026-08-24T00:00:00.000Z",
        "cwd": "D:\\work",
    }


def test_reader_returns_header_and_entries_without_mutating_file(tmp_path: Path) -> None:
    path = tmp_path / "session.jsonl"
    original = _write(
        path,
        [
            _header(),
            {
                "type": "session_info",
                "id": "e1",
                "parentId": None,
                "timestamp": "2026-08-24T00:00:01.000Z",
                "name": "demo",
            },
        ],
    )

    parsed = read_session(path)

    assert parsed.header.id == "s1"
    assert [entry.id for entry in parsed.entries] == ["e1"]
    assert path.read_bytes() == original


@pytest.mark.parametrize(
    ("payload", "line"),
    [
        (b'{"type":"session"}\n', 1),
        (b'{"type":"session","version":3', 1),
        (
            json.dumps(_header()).encode()
            + b'\n{"type":"unknown","id":"e1","parentId":null,"timestamp":"x"}\n',
            2,
        ),
        (json.dumps(_header()).encode() + b"\n" + bytes([0xFF]) + b"\n", 2),
    ],
)
def test_reader_reports_path_and_line_and_preserves_corrupt_bytes(
    tmp_path: Path, payload: bytes, line: int
) -> None:
    path = tmp_path / "broken.jsonl"
    path.write_bytes(payload)
    digest = hashlib.sha256(payload).digest()

    with pytest.raises(SessionCorruptError) as caught:
        read_session(path)

    assert caught.value.path == path.resolve()
    assert caught.value.line == line
    assert str(path.resolve()) in str(caught.value)
    assert f"line {line}" in str(caught.value)
    assert hashlib.sha256(path.read_bytes()).digest() == digest


def test_reader_rejects_header_after_first_record(tmp_path: Path) -> None:
    path = tmp_path / "duplicate-header.jsonl"
    _write(path, [_header(), _header()])

    with pytest.raises(SessionCorruptError, match="line 2"):
        read_session(path)


def test_reader_rejects_unsafe_header_id(tmp_path: Path) -> None:
    path = tmp_path / "unsafe.jsonl"
    header = _header()
    header["id"] = "../escape"
    _write(path, [header])

    with pytest.raises(SessionCorruptError, match="session id"):
        read_session(path)


@pytest.mark.parametrize(
    "entries",
    [
        [
            {
                "type": "session_info",
                "id": "e1",
                "parentId": None,
                "timestamp": "2026-08-24T00:00:01.000Z",
            },
            {
                "type": "session_info",
                "id": "e1",
                "parentId": "e1",
                "timestamp": "2026-08-24T00:00:02.000Z",
            },
        ],
        [
            {
                "type": "session_info",
                "id": "e1",
                "parentId": "missing",
                "timestamp": "2026-08-24T00:00:01.000Z",
            }
        ],
        [
            {
                "type": "session_info",
                "id": "e1",
                "parentId": None,
                "timestamp": "2026-08-24T00:00:01.000Z",
            },
            {
                "type": "session_info",
                "id": "e2",
                "parentId": None,
                "timestamp": "2026-08-24T00:00:02.000Z",
            },
        ],
    ],
)
def test_reader_rejects_invalid_entry_graphs(
    tmp_path: Path, entries: list[dict[str, object]]
) -> None:
    path = tmp_path / "graph.jsonl"
    _write(path, [_header(), *entries])

    with pytest.raises(SessionCorruptError):
        read_session(path)


def test_reader_rejects_invalid_agent_message_at_its_line(tmp_path: Path) -> None:
    path = tmp_path / "message.jsonl"
    _write(
        path,
        [
            _header(),
            {
                "type": "message",
                "id": "e1",
                "parentId": None,
                "timestamp": "2026-08-24T00:00:01.000Z",
                "message": {"role": "assistant", "content": []},
            },
        ],
    )

    with pytest.raises(SessionCorruptError, match="line 2"):
        read_session(path)


def test_reader_rejects_tool_result_without_ancestor_tool_call(tmp_path: Path) -> None:
    path = tmp_path / "tool-result.jsonl"
    _write(
        path,
        [
            _header(),
            {
                "type": "message",
                "id": "e1",
                "parentId": None,
                "timestamp": "2026-08-24T00:00:01.000Z",
                "message": {
                    "role": "toolResult",
                    "toolCallId": "call-1",
                    "toolName": "read",
                    "content": [{"type": "text", "text": "result"}],
                    "isError": False,
                    "timestamp": 1,
                },
            },
        ],
    )

    with pytest.raises(SessionCorruptError, match="tool result"):
        read_session(path)


def test_reader_accepts_tool_result_with_matching_ancestor_call(tmp_path: Path) -> None:
    path = tmp_path / "tool-pair.jsonl"
    usage = {
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
    }
    _write(
        path,
        [
            _header(),
            {
                "type": "message",
                "id": "call",
                "parentId": None,
                "timestamp": "2026-08-24T00:00:01.000Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "toolCall", "id": "call-1", "name": "read", "arguments": {}}
                    ],
                    "api": "test",
                    "provider": "test",
                    "model": "test-model",
                    "usage": usage,
                    "stopReason": "toolUse",
                    "timestamp": 1,
                },
            },
            {
                "type": "message",
                "id": "result",
                "parentId": "call",
                "timestamp": "2026-08-24T00:00:02.000Z",
                "message": {
                    "role": "toolResult",
                    "toolCallId": "call-1",
                    "toolName": "read",
                    "content": [{"type": "text", "text": "ok"}],
                    "isError": False,
                    "timestamp": 2,
                },
            },
        ],
    )

    assert [entry.id for entry in read_session(path).entries] == ["call", "result"]
