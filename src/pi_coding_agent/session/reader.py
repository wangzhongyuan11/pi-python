"""Read Session v3 files without mutation or partial recovery."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from .codec import parse_record
from .errors import EntryValidationError, InvalidSessionIdError, SessionCorruptError
from .ids import validate_session_id
from .models import SessionEntry, SessionHeader
from .validation import validate_session_entries


@dataclass(frozen=True, slots=True)
class ParsedSession:
    path: Path
    header: SessionHeader
    entries: tuple[SessionEntry, ...]


def _parse_line(path: Path, number: int, raw_line: bytes) -> object:
    try:
        text = raw_line.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SessionCorruptError(path, number, "invalid UTF-8") from error
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise SessionCorruptError(path, number, "invalid JSON") from error


def _validate_header_timestamp(path: Path, number: int, value: str) -> None:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        datetime.fromisoformat(normalized)
    except ValueError as error:
        raise SessionCorruptError(path, number, "timestamp is not ISO-8601") from error


def read_session(path: str | Path) -> ParsedSession:
    """Strictly parse a v3 JSONL file, leaving every source byte untouched."""

    resolved = Path(path).resolve()
    raw_lines = resolved.read_bytes().splitlines()
    header: SessionHeader | None = None
    header_line = 1
    entries: list[SessionEntry] = []
    entry_lines: list[int] = []
    for number, raw_line in enumerate(raw_lines, start=1):
        if not raw_line.strip():
            continue
        try:
            record = parse_record(_parse_line(resolved, number, raw_line))
        except ValidationError as error:
            raise SessionCorruptError(
                resolved, number, "record does not match Session v3"
            ) from error
        if header is None:
            if not isinstance(record, SessionHeader):
                raise SessionCorruptError(resolved, number, "first record is not a session header")
            header = record
            header_line = number
            continue
        if isinstance(record, SessionHeader):
            raise SessionCorruptError(resolved, number, "session header may only appear first")
        entries.append(record)
        entry_lines.append(number)
    if header is None:
        raise SessionCorruptError(resolved, 1, "missing session header")
    _validate_header_timestamp(resolved, header_line, header.timestamp)
    try:
        validate_session_id(header.id)
    except InvalidSessionIdError as error:
        raise SessionCorruptError(resolved, header_line, "invalid session id") from error
    try:
        validate_session_entries(tuple(entries))
    except EntryValidationError as error:
        raise SessionCorruptError(resolved, entry_lines[error.entry_index], error.reason) from error
    return ParsedSession(path=resolved, header=header, entries=tuple(entries))


__all__ = ["ParsedSession", "read_session"]
