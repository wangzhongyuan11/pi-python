"""CLI adapter for the session repair command."""

from __future__ import annotations

from pathlib import Path
from typing import TextIO

from ..session.repair import repair_session


def run_session_repair(path: str, *, stdout: TextIO, stderr: TextIO) -> int:
    target = Path(path)
    if not target.is_file():
        stderr.write(f"session file not found: {target}\n")
        return 1
    result = repair_session(target)
    if result.status == "refused":
        stderr.write(f"{result.message}\n")
        return 1
    stdout.write(f"{result.message}\n")
    return 0


__all__ = ["run_session_repair"]
