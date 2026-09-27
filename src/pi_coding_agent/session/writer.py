"""Append-only durability helpers for Session JSONL files."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from pathlib import Path
from typing import BinaryIO

from .codec import dump_record
from .models import SessionEntry, SessionHeader


def encode_record_line(record: SessionHeader | SessionEntry) -> bytes:
    payload = json.dumps(
        dump_record(record),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return payload.encode("utf-8") + b"\n"


def _flush(file: BinaryIO) -> None:
    file.flush()
    os.fsync(file.fileno())


def create_session_file(path: Path, records: Iterable[SessionHeader | SessionEntry]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.open("xb") as file:
        for record in records:
            file.write(encode_record_line(record))
        _flush(file)
    path.chmod(0o600)


def _ends_with_newline(path: Path) -> bool:
    size = path.stat().st_size
    if size == 0:
        return True
    with path.open("rb") as file:
        file.seek(-1, os.SEEK_END)
        return file.read(1) == b"\n"


def append_session_record(path: Path, record: SessionEntry) -> None:
    payload = encode_record_line(record)
    if not _ends_with_newline(path):
        # A file whose final line lacks the newline separator (for example a
        # hand-edited or truncated copy) must not grow a concatenated record.
        payload = b"\n" + payload
    with path.open("ab") as file:
        file.write(payload)
        _flush(file)


__all__ = ["append_session_record", "create_session_file", "encode_record_line"]
