"""Typed errors for Session persistence boundaries."""

from __future__ import annotations

from pathlib import Path


class SessionError(Exception):
    """Base class for expected Session failures."""


class SessionCorruptError(SessionError):
    """A Session JSONL file failed strict validation."""

    def __init__(self, path: Path, line: int, reason: str) -> None:
        self.path = path.resolve()
        self.line = line
        self.reason = reason
        super().__init__(f"Invalid session file {self.path} at line {line}: {reason}")


class SessionGraphError(SessionError):
    """Session entries do not form one valid append-only tree."""


class EntryValidationError(SessionGraphError):
    """One entry failed graph or AgentMessage validation."""

    def __init__(self, entry_index: int, reason: str) -> None:
        self.entry_index = entry_index
        self.reason = reason
        super().__init__(reason)


class SessionNotFoundError(SessionError):
    """No Session matched an exact path or id."""


class InvalidSessionIdError(SessionError):
    """A caller supplied an unsafe or malformed Session id."""


__all__ = [
    "EntryValidationError",
    "InvalidSessionIdError",
    "SessionCorruptError",
    "SessionError",
    "SessionGraphError",
    "SessionNotFoundError",
]
