"""Explicit, read-only import of mature upstream Pi Session v3 files."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import cast

from .atomic import atomic_create
from .errors import SessionImportError
from .models import ImportResult
from .reader import read_session
from .tree import SessionTree


def _encoded_cwd(cwd: str) -> str:
    resolved = str(Path(cwd).resolve()).lstrip("/\\")
    encoded = resolved.replace("/", "-").replace("\\", "-").replace(":", "-")
    return f"--{encoded}--"


def _default_session_dir(cwd: str) -> Path:
    configured = os.environ.get("PI_PYTHON_AGENT_DIR")
    agent_dir = (
        Path(configured).expanduser() if configured else Path.home() / ".pi-python" / "agent"
    )
    return agent_dir.resolve() / "sessions" / _encoded_cwd(cwd)


def _reject_old_version(source: Path, data: bytes) -> None:
    for raw_line in data.splitlines():
        if not raw_line.strip():
            continue
        try:
            candidate = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        if isinstance(candidate, dict) and cast("dict[str, object]", candidate).get("version") != 3:
            raise SessionImportError(
                "only Session version 3 can be imported; migrate older sessions with upstream Pi"
            )
        return


def import_pi_session(
    source: str | Path,
    *,
    session_dir: str | Path | None = None,
) -> ImportResult:
    """Validate a source v3 file, then copy its exact bytes to a new destination."""

    source_file = Path(source).resolve()
    data = source_file.read_bytes()
    _reject_old_version(source_file, data)
    parsed = read_session(source_file)
    SessionTree.build(parsed.entries)
    destination_dir = (
        _default_session_dir(parsed.header.cwd)
        if session_dir is None
        else Path(session_dir).resolve()
    )
    timestamp = parsed.header.timestamp.replace(":", "-").replace(".", "-")
    session_file = destination_dir / f"{timestamp}_{parsed.header.id}.jsonl"
    atomic_create(session_file, data)
    return ImportResult(
        session_id=parsed.header.id,
        session_file=session_file,
        source_file=source_file,
    )


__all__ = ["import_pi_session"]
