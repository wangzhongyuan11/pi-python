"""CLI adapter for explicit, read-only upstream Session import."""

from __future__ import annotations

import json
from typing import TextIO

from ..sdk import import_pi_session
from ..session.errors import SessionError


def run_import_session(
    source: str,
    *,
    session_dir: str | None,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    try:
        result = import_pi_session(source, session_dir=session_dir)
    except (OSError, SessionError) as error:
        stderr.write(f"{error}\n")
        return 1
    payload = {
        "sessionId": result.session_id,
        "sessionFile": str(result.session_file),
        "sourceFile": str(result.source_file),
    }
    stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    stdout.write("\n")
    return 0


__all__ = ["run_import_session"]
