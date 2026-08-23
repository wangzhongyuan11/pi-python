"""Read-only structured Session export projections."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .catalog import open_session
from .context import SessionContext, project_session_context
from .errors import SessionGraphError
from .manager import SessionManager
from .models import SessionEntry, SessionHeader
from .tree import SessionTree


@dataclass(frozen=True, slots=True)
class SessionTranscript:
    session_id: str
    source: Path | None
    header: SessionHeader
    leaf_id: str
    entries: tuple[SessionEntry, ...]
    context: SessionContext


def export_session(
    source: SessionManager | str | Path,
    *,
    leaf_id: str | None = None,
) -> SessionTranscript:
    """Project a Session branch without creating or modifying any file."""

    manager = source if isinstance(source, SessionManager) else open_session(source)
    selected_leaf = leaf_id or manager.leaf_id
    if selected_leaf is None:
        raise SessionGraphError("cannot export an empty session")
    tree = SessionTree.build(manager.entries)
    entries = tree.active_path(selected_leaf)
    return SessionTranscript(
        session_id=manager.header.id,
        source=manager.path,
        header=manager.header,
        leaf_id=selected_leaf,
        entries=entries,
        context=project_session_context(tree, selected_leaf),
    )


__all__ = ["SessionTranscript", "export_session"]
