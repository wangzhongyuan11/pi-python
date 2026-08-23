"""Read-only Session path/id resolution and catalog operations."""

from __future__ import annotations

from pathlib import Path

from .errors import SessionNotFoundError
from .ids import validate_session_id
from .manager import SessionManager
from .reader import read_session
from .tree import SessionTree


def _looks_like_path(value: str | Path) -> bool:
    if isinstance(value, Path):
        return True
    return Path(value).is_absolute() or value.endswith(".jsonl") or "/" in value or "\\" in value


def _resolve(value: str | Path, session_dir: str | Path | None) -> Path:
    if _looks_like_path(value):
        path = Path(value).resolve()
        if not path.is_file():
            raise SessionNotFoundError(f"session file not found: {path}")
        return path
    session_id = validate_session_id(str(value))
    if session_dir is None:
        raise SessionNotFoundError("session_dir is required when opening by id")
    directory = Path(session_dir).resolve()
    candidates = sorted(directory.glob(f"*_{session_id}.jsonl")) if directory.is_dir() else []
    matches: list[Path] = []
    for candidate in candidates:
        parsed = read_session(candidate)
        if parsed.header.id == session_id:
            matches.append(candidate.resolve())
    if len(matches) != 1:
        raise SessionNotFoundError(
            f"expected one session with id {session_id!r}, found {len(matches)}"
        )
    return matches[0]


def open_session(
    value: str | Path,
    *,
    session_dir: str | Path | None = None,
) -> SessionManager:
    """Open one exact Session without repairing or touching its source file."""

    path = _resolve(value, session_dir)
    parsed = read_session(path)
    SessionTree.build(parsed.entries)
    return SessionManager(
        header=parsed.header,
        path=parsed.path,
        entries=parsed.entries,
        persisted=True,
    )


__all__ = ["open_session", "validate_session_id"]
