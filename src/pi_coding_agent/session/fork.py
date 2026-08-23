"""Create a new Session from one selected source branch."""

from __future__ import annotations

from pathlib import Path

from .atomic import atomic_create
from .ids import validate_session_id
from .manager import SessionManager
from .models import SessionHeader
from .reader import read_session
from .tree import SessionTree
from .writer import encode_record_line


def _filename(timestamp: str, session_id: str) -> str:
    return f"{timestamp.replace(':', '-').replace('.', '-')}_{session_id}.jsonl"


def fork_session(
    source: str | Path,
    *,
    leaf_id: str,
    target_cwd: str | Path,
    session_dir: str | Path,
    session_id: str,
    timestamp: str,
) -> SessionManager:
    """Copy one active path into a newly identified, atomically written Session."""

    parsed = read_session(source)
    validate_session_id(session_id)
    path = SessionTree.build(parsed.entries).active_path(leaf_id)
    target = Path(session_dir).resolve() / _filename(timestamp, session_id)
    header = SessionHeader(
        type="session",
        version=3,
        id=session_id,
        timestamp=timestamp,
        cwd=str(Path(target_cwd).resolve()),
        parent_session=str(parsed.path),
    )
    payload = b"".join(encode_record_line(record) for record in (header, *path))
    atomic_create(target, payload)
    return SessionManager(
        header=header,
        path=target,
        entries=path,
        persisted=True,
    )


__all__ = ["fork_session"]
