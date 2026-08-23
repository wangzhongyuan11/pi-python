"""Mature synchronous append-only Session manager."""

from __future__ import annotations

from pathlib import Path

from pi_agent import AgentMessage

from .errors import SessionGraphError
from .ids import validate_session_id
from .models import MessageEntry, SessionEntry, SessionHeader
from .validation import SessionEntryValidator
from .writer import append_session_record, create_session_file


def _filename(timestamp: str, session_id: str) -> str:
    safe_timestamp = timestamp.replace(":", "-").replace(".", "-")
    return f"{safe_timestamp}_{session_id}.jsonl"


class SessionManager:
    def __init__(
        self,
        *,
        header: SessionHeader,
        path: Path | None,
        entries: tuple[SessionEntry, ...] = (),
        persisted: bool = False,
    ) -> None:
        self.header = header
        self.path = path
        self._entries = list(entries)
        self._persisted = persisted
        self.leaf_id = entries[-1].id if entries else None
        self._validator = SessionEntryValidator()
        for entry in entries:
            message = self._validator.validate_next(entry)
            self._validator.accept(entry, message)

    @classmethod
    def create(
        cls,
        *,
        cwd: str | Path,
        session_dir: str | Path,
        session_id: str,
        timestamp: str,
        parent_session: str | None = None,
    ) -> SessionManager:
        validate_session_id(session_id)
        header_fields: dict[str, object] = {
            "type": "session",
            "version": 3,
            "id": session_id,
            "timestamp": timestamp,
            "cwd": str(Path(cwd).resolve()),
        }
        if parent_session is not None:
            header_fields["parent_session"] = parent_session
        header = SessionHeader.model_validate(header_fields)
        path = Path(session_dir).resolve() / _filename(timestamp, session_id)
        return cls(header=header, path=path)

    @classmethod
    def in_memory(
        cls,
        *,
        cwd: str | Path,
        session_id: str,
        timestamp: str,
    ) -> SessionManager:
        validate_session_id(session_id)
        header = SessionHeader(
            type="session",
            version=3,
            id=session_id,
            timestamp=timestamp,
            cwd=str(Path(cwd).resolve()),
        )
        return cls(header=header, path=None)

    @property
    def entries(self) -> tuple[SessionEntry, ...]:
        return tuple(self._entries)

    def append(self, entry: SessionEntry) -> None:
        if entry.parent_id != self.leaf_id:
            raise SessionGraphError(
                f"new entry parent {entry.parent_id!r} does not match current leaf {self.leaf_id!r}"
            )
        message = self._validator.validate_next(entry)
        if self.path is None:
            self._advance(entry, message)
            return
        if not self._persisted:
            if not _is_assistant_message(entry):
                self._advance(entry, message)
                return
            create_session_file(self.path, (self.header, *self._entries, entry))
            self._persisted = True
        else:
            append_session_record(self.path, entry)
        self._advance(entry, message)

    def _advance(self, entry: SessionEntry, message: AgentMessage | None) -> None:
        self._entries.append(entry)
        self.leaf_id = entry.id
        self._validator.accept(entry, message)


def _is_assistant_message(entry: SessionEntry) -> bool:
    return isinstance(entry, MessageEntry) and entry.message.get("role") == "assistant"


__all__ = ["SessionManager"]
