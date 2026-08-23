"""Operations-backed directory listing tool behavior."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from .operations import FilesystemOperations
from .paths import resolve_tool_path
from .search import MAX_OUTPUT_BYTES

DEFAULT_LIST_LIMIT = 500


class ListToolError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class ListResult:
    text: str
    entries: tuple[str, ...]
    limit_reached: int | None
    bytes_truncated: bool


def _limit(value: int | None) -> int:
    if value is None:
        return DEFAULT_LIST_LIMIT
    if isinstance(value, bool) or value <= 0:
        raise ListToolError("limit must be a positive integer")
    return value


def _truncate_head(entries: tuple[str, ...]) -> tuple[str, bool]:
    selected: list[str] = []
    size = 0
    for entry in entries:
        encoded = len(entry.encode("utf-8")) + int(bool(selected))
        if size + encoded > MAX_OUTPUT_BYTES:
            return "\n".join(selected), True
        selected.append(entry)
        size += encoded
    return "\n".join(selected), False


async def list_directory(
    path: str | Path = ".",
    *,
    cwd: Path,
    operations: FilesystemOperations,
    limit: int | None = None,
    abort_event: asyncio.Event | None = None,
) -> ListResult:
    effective_limit = _limit(limit)
    if abort_event is not None and abort_event.is_set():
        raise ListToolError("List operation aborted")
    resolved = resolve_tool_path(path, cwd=cwd)
    try:
        scanned = await operations.scan_directory(resolved)
    except OSError as error:
        raise ListToolError(f"Could not list {resolved}: {error}") from None
    if abort_event is not None and abort_event.is_set():
        raise ListToolError("List operation aborted")

    ordered = sorted(scanned, key=lambda entry: (entry.name.casefold(), entry.name))
    formatted = tuple(f"{entry.name}/" if entry.is_dir else entry.name for entry in ordered)
    limited = formatted[:effective_limit]
    output, bytes_truncated = _truncate_head(limited)
    limit_reached = effective_limit if len(formatted) > effective_limit else None
    notices: list[str] = []
    if limit_reached is not None:
        notices.append(
            f"{effective_limit} entries limit reached. Use limit={effective_limit * 2} for more"
        )
    if bytes_truncated:
        notices.append("50KB output limit reached")
    if notices:
        output += f"\n\n[{'. '.join(notices)}]"
    if not output:
        output = "(empty directory)"
    return ListResult(
        text=output,
        entries=limited,
        limit_reached=limit_reached,
        bytes_truncated=bytes_truncated,
    )


__all__ = ["ListResult", "ListToolError", "list_directory"]
