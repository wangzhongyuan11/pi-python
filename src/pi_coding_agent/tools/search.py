"""Operations-backed grep and find tool behavior."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from .operations import SearchMatch, SearchOperations
from .paths import resolve_tool_path

DEFAULT_GREP_LIMIT = 100
DEFAULT_FIND_LIMIT = 1_000
MAX_OUTPUT_BYTES = 50 * 1024
MAX_MATCH_LINE_CHARS = 500


class SearchToolError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class GrepResult:
    text: str
    matches: tuple[SearchMatch, ...]
    limit_reached: int | None
    lines_truncated: bool
    bytes_truncated: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class FindResult:
    text: str
    paths: tuple[str, ...]
    limit_reached: int | None
    bytes_truncated: bool


def _limit(value: int | None, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or value <= 0:
        raise SearchToolError("limit must be a positive integer")
    return value


def _relative(path: Path, root: Path) -> str:
    resolved = path.resolve(strict=False)
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return resolved.name


def _truncate_head(lines: list[str]) -> tuple[str, bool]:
    selected: list[str] = []
    size = 0
    for line in lines:
        encoded = len(line.encode("utf-8")) + int(bool(selected))
        if size + encoded > MAX_OUTPUT_BYTES:
            return "\n".join(selected), True
        selected.append(line)
        size += encoded
    return "\n".join(selected), False


async def grep_files(
    pattern: str,
    path: str | Path = ".",
    *,
    cwd: Path,
    operations: SearchOperations,
    limit: int | None = None,
    include_hidden: bool = True,
    abort_event: asyncio.Event | None = None,
) -> GrepResult:
    effective_limit = _limit(limit, DEFAULT_GREP_LIMIT)
    if abort_event is not None and abort_event.is_set():
        raise SearchToolError("Search operation aborted")
    root = resolve_tool_path(path, cwd=cwd)
    try:
        matches = await operations.grep(pattern, root, include_hidden=include_hidden)
    except OSError as error:
        raise SearchToolError(f"Could not search {root}: {error}") from None
    if abort_event is not None and abort_event.is_set():
        raise SearchToolError("Search operation aborted")

    ordered = sorted(
        matches,
        key=lambda match: (
            _relative(match.path, root).casefold(),
            _relative(match.path, root),
            match.line,
            match.column,
        ),
    )
    limited = tuple(ordered[:effective_limit])
    lines: list[str] = []
    lines_truncated = False
    for match in limited:
        text = match.text
        if len(text) > MAX_MATCH_LINE_CHARS:
            text = f"{text[:MAX_MATCH_LINE_CHARS]}... [truncated]"
            lines_truncated = True
        lines.append(f"{_relative(match.path, root)}:{match.line}:{match.column}:{text}")
    output, bytes_truncated = _truncate_head(lines)
    limit_reached = effective_limit if len(ordered) > effective_limit else None
    notices: list[str] = []
    if limit_reached is not None:
        notices.append(f"{effective_limit} matches limit reached")
    if bytes_truncated:
        notices.append("50KB output limit reached")
    if notices:
        output += f"\n\n[{'. '.join(notices)}]"
    if not output:
        output = "No matches found"
    return GrepResult(
        text=output,
        matches=limited,
        limit_reached=limit_reached,
        lines_truncated=lines_truncated,
        bytes_truncated=bytes_truncated,
    )


async def find_files(
    pattern: str,
    path: str | Path = ".",
    *,
    cwd: Path,
    operations: SearchOperations,
    limit: int | None = None,
    include_hidden: bool = True,
    abort_event: asyncio.Event | None = None,
) -> FindResult:
    effective_limit = _limit(limit, DEFAULT_FIND_LIMIT)
    if abort_event is not None and abort_event.is_set():
        raise SearchToolError("Search operation aborted")
    root = resolve_tool_path(path, cwd=cwd)
    try:
        paths = await operations.find(pattern, root, include_hidden=include_hidden)
    except OSError as error:
        raise SearchToolError(f"Could not search {root}: {error}") from None
    if abort_event is not None and abort_event.is_set():
        raise SearchToolError("Search operation aborted")

    relative = sorted(
        (_relative(candidate, root) for candidate in paths),
        key=lambda item: (item.casefold(), item),
    )
    limited = tuple(relative[:effective_limit])
    output, bytes_truncated = _truncate_head(list(limited))
    limit_reached = effective_limit if len(relative) > effective_limit else None
    notices: list[str] = []
    if limit_reached is not None:
        notices.append(f"{effective_limit} results limit reached")
    if bytes_truncated:
        notices.append("50KB output limit reached")
    if notices:
        output += f"\n\n[{'. '.join(notices)}]"
    if not output:
        output = "No files found matching pattern"
    return FindResult(
        text=output,
        paths=limited,
        limit_reached=limit_reached,
        bytes_truncated=bytes_truncated,
    )


__all__ = [
    "FindResult",
    "GrepResult",
    "SearchToolError",
    "find_files",
    "grep_files",
]
