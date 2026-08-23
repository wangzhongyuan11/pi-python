"""Atomic UTF-8 file writes for coding-agent tools."""

from __future__ import annotations

import asyncio
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .paths import resolve_tool_path


class WriteToolError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class WriteResult:
    path: Path
    bytes_written: int


def _replace_file(path: Path, data: bytes, abort_event: asyncio.Event | None) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if abort_event is not None and abort_event.is_set():
            raise WriteToolError("Write operation aborted")
        os.replace(temporary, path)
        try:
            directory = os.open(path.parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(directory)
        except OSError:
            pass
        finally:
            os.close(directory)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


async def write_file(
    path: str | Path,
    content: str,
    *,
    cwd: Path,
    abort_event: asyncio.Event | None = None,
) -> WriteResult:
    if abort_event is not None and abort_event.is_set():
        raise WriteToolError("Write operation aborted")
    resolved = resolve_tool_path(path, cwd=cwd)
    data = content.encode("utf-8")
    try:
        await asyncio.to_thread(resolved.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(_replace_file, resolved, data, abort_event)
    except WriteToolError:
        raise
    except OSError as error:
        reason = error.strerror or type(error).__name__
        raise WriteToolError(f"Could not write {resolved}: {reason}") from None
    return WriteResult(path=resolved, bytes_written=len(data))


__all__ = ["WriteResult", "WriteToolError", "write_file"]
