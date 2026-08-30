"""Head-truncating text file reader with source-compatible continuation hints."""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .paths import resolve_tool_path

DEFAULT_MAX_LINES = 2_000
DEFAULT_MAX_BYTES = 50 * 1024

_IMAGE_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)
_INLINE_IMAGE_MIMES = frozenset({"image/png", "image/jpeg", "image/gif", "image/webp"})


def detect_image_mime(data: bytes) -> str | None:
    """Identify an image file by magic bytes; returns None for text files."""
    for magic, mime in _IMAGE_MAGIC:
        if data.startswith(magic):
            return mime
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"BM"):
        return "image/bmp"
    return None


class ReadToolError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class ReadResult:
    path: Path
    text: str
    start_line: int
    end_line: int
    total_lines: int
    truncated: bool
    truncated_by: Literal["lines", "bytes"] | None = None
    first_line_exceeds_limit: bool = False
    next_offset: int | None = None
    image_mime: str | None = None
    image_data: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class _Head:
    content: str
    output_lines: int
    truncated: bool
    truncated_by: Literal["lines", "bytes"] | None
    first_line_exceeds_limit: bool


def _format_size(size: int) -> str:
    if size < 1_024:
        return f"{size}B"
    if size < 1_024 * 1_024:
        return f"{size / 1_024:.1f}KB"
    return f"{size / (1_024 * 1_024):.1f}MB"


def _counted_lines(content: str) -> list[str]:
    if not content:
        return []
    lines = content.split("\n")
    if content.endswith("\n"):
        lines.pop()
    return lines


def _truncate_head(content: str) -> _Head:
    lines = _counted_lines(content)
    total_bytes = len(content.encode("utf-8"))
    if len(lines) <= DEFAULT_MAX_LINES and total_bytes <= DEFAULT_MAX_BYTES:
        return _Head(
            content=content,
            output_lines=len(lines),
            truncated=False,
            truncated_by=None,
            first_line_exceeds_limit=False,
        )
    if lines and len(lines[0].encode("utf-8")) > DEFAULT_MAX_BYTES:
        return _Head(
            content="",
            output_lines=0,
            truncated=True,
            truncated_by="bytes",
            first_line_exceeds_limit=True,
        )

    output: list[str] = []
    output_bytes = 0
    truncated_by: Literal["lines", "bytes"] = "lines"
    for index, line in enumerate(lines[:DEFAULT_MAX_LINES]):
        encoded = len(line.encode("utf-8")) + (1 if index > 0 else 0)
        if output_bytes + encoded > DEFAULT_MAX_BYTES:
            truncated_by = "bytes"
            break
        output.append(line)
        output_bytes += encoded
    return _Head(
        content="\n".join(output),
        output_lines=len(output),
        truncated=True,
        truncated_by=truncated_by,
        first_line_exceeds_limit=False,
    )


def _positive_integer(name: str, value: int | None, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or value <= 0:
        raise ReadToolError(f"{name} must be a positive integer")
    return value


async def read_file(
    path: str | Path,
    *,
    cwd: Path,
    offset: int | None = None,
    limit: int | None = None,
    abort_event: asyncio.Event | None = None,
) -> ReadResult:
    if abort_event is not None and abort_event.is_set():
        raise ReadToolError("Read operation aborted")
    start_line = _positive_integer("offset", offset, 1)
    selected_limit = None if limit is None else _positive_integer("limit", limit, 1)
    resolved = resolve_tool_path(path, cwd=cwd)
    try:
        data = await asyncio.to_thread(resolved.read_bytes)
    except OSError as error:
        reason = error.strerror or type(error).__name__
        raise ReadToolError(f"Could not read {resolved}: {reason}") from None
    if abort_event is not None and abort_event.is_set():
        raise ReadToolError("Read operation aborted")

    image_mime = detect_image_mime(data)
    if image_mime is not None:
        # Image reads ignore offset/limit and are never line-truncated.
        if image_mime in _INLINE_IMAGE_MIMES:
            return ReadResult(
                path=resolved,
                text=f"Read image file [{image_mime}]",
                start_line=1,
                end_line=1,
                total_lines=1,
                truncated=False,
                image_mime=image_mime,
                image_data=base64.b64encode(data).decode("ascii"),
            )
        return ReadResult(
            path=resolved,
            text=(
                f"Read image file [{image_mime}]\n"
                f"[Image omitted: providers accept png/jpeg/gif/webp inline; "
                f"convert the {image_mime} file to one of those formats first.]"
            ),
            start_line=1,
            end_line=1,
            total_lines=1,
            truncated=False,
        )

    text = data.decode("utf-8", errors="replace")
    all_lines = text.split("\n")
    start_index = start_line - 1
    if start_index >= len(all_lines):
        raise ReadToolError(
            f"Offset {start_line} is beyond end of file ({len(all_lines)} lines total)"
        )
    end_index = (
        len(all_lines)
        if selected_limit is None
        else min(start_index + selected_limit, len(all_lines))
    )
    selected = "\n".join(all_lines[start_index:end_index])
    head = _truncate_head(selected)

    if head.first_line_exceeds_limit:
        first_line_bytes = len(all_lines[start_index].encode("utf-8"))
        output = (
            f"[Line {start_line} is {_format_size(first_line_bytes)}, exceeds "
            f"{_format_size(DEFAULT_MAX_BYTES)} limit. Use bash to inspect this line in chunks.]"
        )
        end_line = start_line
        next_offset = None
    elif head.truncated:
        end_line = start_line + head.output_lines - 1
        next_offset = end_line + 1
        suffix = (
            f" ({_format_size(DEFAULT_MAX_BYTES)} limit)" if head.truncated_by == "bytes" else ""
        )
        output = (
            f"{head.content}\n\n[Showing lines {start_line}-{end_line} of {len(all_lines)}"
            f"{suffix}. Use offset={next_offset} to continue.]"
        )
    elif end_index < len(all_lines):
        remaining = len(all_lines) - end_index
        next_offset = end_index + 1
        end_line = end_index
        output = (
            f"{head.content}\n\n[{remaining} more lines in file. "
            f"Use offset={next_offset} to continue.]"
        )
    else:
        output = head.content
        next_offset = None
        end_line = start_line + max(head.output_lines, 1) - 1

    return ReadResult(
        path=resolved,
        text=output,
        start_line=start_line,
        end_line=end_line,
        total_lines=len(all_lines),
        truncated=head.truncated,
        truncated_by=head.truncated_by,
        first_line_exceeds_limit=head.first_line_exceeds_limit,
        next_offset=next_offset,
    )


__all__ = [
    "DEFAULT_MAX_BYTES",
    "DEFAULT_MAX_LINES",
    "ReadResult",
    "ReadToolError",
    "detect_image_mime",
    "read_file",
]
