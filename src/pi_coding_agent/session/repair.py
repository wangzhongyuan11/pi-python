"""Trailing torn-line repair for v3 Session files (Python-only divergence)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .atomic import atomic_write
from .errors import SessionError
from .reader import read_session

type RepairStatus = Literal["clean", "truncated", "refused"]


@dataclass(frozen=True, slots=True)
class RepairResult:
    status: RepairStatus
    message: str
    removed_bytes: int = 0


def _is_valid_json_line(line: bytes) -> bool:
    try:
        json.loads(line.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False
    return True


def repair_session(path: str | Path) -> RepairResult:
    """Repair a Session file whose last line is torn mid-write.

    Only the final line may be damaged, and only at the JSON level. Structural
    corruption anywhere, damage before the last line, or a torn header is
    refused so legal v3 bytes are never altered.
    """
    resolved = Path(path).resolve()
    raw = resolved.read_bytes()
    try:
        read_session(resolved)
    except SessionError:
        pass
    else:
        return RepairResult("clean", "no repair needed", 0)

    non_empty = [line for line in raw.splitlines() if line.strip()]
    if not non_empty:
        return RepairResult("refused", "cannot repair: file has no records", 0)

    last = non_empty[-1]
    if _is_valid_json_line(last):
        return RepairResult(
            "refused",
            "cannot repair: the last record is complete but structurally invalid",
            0,
        )
    kept = non_empty[:-1]
    if not kept:
        return RepairResult(
            "refused",
            "cannot repair: the header record itself is torn",
            0,
        )

    kept_payload = b"".join(line + b"\n" for line in kept)
    temporary = resolved.with_name(resolved.name + ".repair.tmp")
    try:
        atomic_write(temporary, kept_payload)
        try:
            read_session(temporary)
        except SessionError as error:
            return RepairResult(
                "refused",
                f"cannot repair: keeping the prefix would still be invalid ({error})",
                0,
            )
    finally:
        temporary.unlink(missing_ok=True)

    removed = len(raw) - len(kept_payload)
    atomic_write(resolved, kept_payload)
    return RepairResult(
        "truncated",
        f"repaired: truncated torn trailing record ({removed} bytes removed)",
        removed,
    )


__all__ = ["RepairResult", "RepairStatus", "repair_session"]
