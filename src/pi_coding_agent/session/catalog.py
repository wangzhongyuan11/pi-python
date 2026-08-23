"""Read-only Session path/id resolution and catalog operations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .errors import SessionError, SessionNotFoundError
from .ids import validate_session_id
from .manager import SessionManager
from .models import SessionInfoEntry
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


@dataclass(frozen=True, slots=True)
class SessionSummary:
    path: Path
    id: str
    cwd: str
    name: str | None
    created: str
    modified_ns: int
    entry_count: int


@dataclass(frozen=True, slots=True)
class SessionDiagnostic:
    path: Path
    message: str


@dataclass(frozen=True, slots=True)
class SessionCatalog:
    sessions: tuple[SessionSummary, ...]
    diagnostics: tuple[SessionDiagnostic, ...]


def list_sessions(*, cwd: str | Path, session_dir: str | Path) -> SessionCatalog:
    """List valid Sessions while reporting each corrupt file independently."""

    directory = Path(session_dir).resolve()
    resolved_cwd = Path(cwd).resolve()
    sessions: list[SessionSummary] = []
    diagnostics: list[SessionDiagnostic] = []
    if not directory.is_dir():
        return SessionCatalog(sessions=(), diagnostics=())
    for path in sorted(directory.glob("*.jsonl")):
        try:
            manager = open_session(path)
            if Path(manager.header.cwd).resolve() != resolved_cwd:
                continue
            name: str | None = None
            for entry in manager.entries:
                if isinstance(entry, SessionInfoEntry):
                    name = entry.name.strip() if entry.name and entry.name.strip() else None
            sessions.append(
                SessionSummary(
                    path=path.resolve(),
                    id=manager.header.id,
                    cwd=manager.header.cwd,
                    name=name,
                    created=manager.header.timestamp,
                    modified_ns=path.stat().st_mtime_ns,
                    entry_count=len(manager.entries),
                )
            )
        except (OSError, SessionError) as error:
            diagnostics.append(SessionDiagnostic(path=path.resolve(), message=str(error)))
    sessions.sort(key=lambda item: item.modified_ns, reverse=True)
    return SessionCatalog(sessions=tuple(sessions), diagnostics=tuple(diagnostics))


__all__ = [
    "SessionCatalog",
    "SessionDiagnostic",
    "SessionSummary",
    "list_sessions",
    "open_session",
    "validate_session_id",
]
