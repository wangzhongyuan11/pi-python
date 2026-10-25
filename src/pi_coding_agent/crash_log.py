"""P15.5/1.1.0 gap closure: crash-log.

On an unhandled top-level exception the recent session transcript and the
error are written under the agent dir (``crash/<timestamp>/``) so a crashed
run can be inspected afterwards. Best-effort: logging failures never mask
the original error.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path


def write_crash_log(
    agent_dir: Path,
    error: BaseException,
    *,
    session_path: Path | None = None,
    transcript_entries: list[dict[str, object]] | None = None,
    now_ms: int | None = None,
) -> Path | None:
    """Write a crash bundle; returns the directory or None when skipped."""

    try:
        stamp = time.strftime(
            "%Y%m%dT%H%M%S", time.localtime((now_ms / 1000) if now_ms else time.time())
        )
        crash_dir = Path(agent_dir) / "crash" / f"{stamp}-{os.getpid()}"
        crash_dir.mkdir(parents=True, exist_ok=True)
        (crash_dir / "error.txt").write_text(
            "".join(__import__("traceback").format_exception(error))[-20000:],
            encoding="utf-8",
        )
        meta: dict[str, object] = {
            "errorType": type(error).__name__,
            "message": str(error)[:2000],
            "writtenAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "sessionPath": str(session_path) if session_path else None,
        }
        (crash_dir / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
        if transcript_entries is not None:
            lines = [json.dumps(entry, ensure_ascii=False) for entry in transcript_entries[-100:]]
            (crash_dir / "recent-entries.jsonl").write_text(
                "\n".join(lines) + "\n", encoding="utf-8"
            )
        return crash_dir
    except OSError:
        return None


__all__ = ["write_crash_log"]
