"""Bounded bash output accumulation with full-output spill files."""

from __future__ import annotations

import codecs
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

DEFAULT_MAX_LINES = 2_000
DEFAULT_MAX_BYTES = 50 * 1024
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


@dataclass(frozen=True, slots=True, kw_only=True)
class OutputSnapshot:
    content: str
    truncated: bool
    truncated_by: Literal["lines", "bytes"] | None
    total_lines: int
    total_bytes: int
    output_lines: int
    output_bytes: int
    full_output_path: Path | None
    last_line_partial: bool = False


def _sanitize(text: str) -> str:
    without_ansi = _ANSI_ESCAPE.sub("", text)
    return "".join(
        character for character in without_ansi if character in "\t\n\r" or ord(character) >= 0x20
    ).replace("\r", "")


def _utf8_tail(text: str, limit: int) -> str:
    data = text.encode("utf-8")
    if len(data) <= limit:
        return text
    start = len(data) - limit
    while start < len(data) and data[start] & 0xC0 == 0x80:
        start += 1
    return data[start:].decode("utf-8")


class OutputAccumulator:
    def __init__(
        self,
        *,
        max_lines: int = DEFAULT_MAX_LINES,
        max_bytes: int = DEFAULT_MAX_BYTES,
        temp_dir: Path | None = None,
    ) -> None:
        self._max_lines = max_lines
        self._max_bytes = max_bytes
        self._temp_dir = temp_dir
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._raw_chunks: list[bytes] = []
        self._tail = ""
        self._total_raw_bytes = 0
        self._total_decoded_bytes = 0
        self._newline_count = 0
        self._saw_text = False
        self._ends_with_newline = False
        self._full_output_path: Path | None = None
        self._full_output = None
        self._finished = False

    @property
    def total_lines(self) -> int:
        return self._newline_count + int(self._saw_text and not self._ends_with_newline)

    def append(self, data: bytes) -> None:
        if self._finished or not data:
            return
        self._total_raw_bytes += len(data)
        if self._full_output is None:
            self._raw_chunks.append(data)
        else:
            self._full_output.write(data)
        self._append_text(self._decoder.decode(data, final=False))
        if self._should_spill():
            self._ensure_full_output()

    def _append_text(self, text: str) -> None:
        if not text:
            return
        self._saw_text = True
        self._ends_with_newline = text.endswith("\n")
        self._newline_count += text.count("\n")
        self._total_decoded_bytes += len(text.encode("utf-8"))
        self._tail += text
        rolling_limit = max(self._max_bytes * 2, 1)
        if len(self._tail.encode("utf-8")) > rolling_limit * 2:
            self._tail = _utf8_tail(self._tail, rolling_limit)

    def _should_spill(self) -> bool:
        return self._total_raw_bytes > self._max_bytes or self.total_lines > self._max_lines

    def _ensure_full_output(self) -> None:
        if self._full_output is not None:
            return
        descriptor, name = tempfile.mkstemp(
            prefix="pi-bash-",
            suffix=".log",
            dir=self._temp_dir,
        )
        self._full_output_path = Path(name)
        self._full_output = os.fdopen(descriptor, "wb")
        for chunk in self._raw_chunks:
            self._full_output.write(chunk)
        self._raw_chunks.clear()

    def finish(self) -> None:
        if self._finished:
            return
        self._append_text(self._decoder.decode(b"", final=True))
        if self._should_spill():
            self._ensure_full_output()
        if self._full_output is not None:
            self._full_output.flush()
            os.fsync(self._full_output.fileno())
            self._full_output.close()
            self._full_output = None
        self._finished = True

    def snapshot(self) -> OutputSnapshot:
        text = _sanitize(self._tail)
        total_bytes = self._total_decoded_bytes
        truncated = total_bytes > self._max_bytes or self.total_lines > self._max_lines
        truncated_by: Literal["lines", "bytes"] | None
        if not truncated:
            content = text
            truncated_by = None
            partial = False
        else:
            lines = text.split("\n")
            if text.endswith("\n"):
                lines.pop()
            selected = lines[-self._max_lines :]
            truncated_by = "bytes" if total_bytes > self._max_bytes else "lines"
            partial = False
            while len(selected) > 1 and len("\n".join(selected).encode("utf-8")) > self._max_bytes:
                selected.pop(0)
                truncated_by = "bytes"
            content = "\n".join(selected)
            if len(content.encode("utf-8")) > self._max_bytes:
                content = _utf8_tail(content, self._max_bytes)
                truncated_by = "bytes"
                partial = True

        output_lines = 0 if not content else len(content.split("\n"))
        return OutputSnapshot(
            content=content,
            truncated=truncated,
            truncated_by=truncated_by,
            total_lines=self.total_lines,
            total_bytes=total_bytes,
            output_lines=output_lines,
            output_bytes=len(content.encode("utf-8")),
            full_output_path=self._full_output_path,
            last_line_partial=partial,
        )


__all__ = [
    "DEFAULT_MAX_BYTES",
    "DEFAULT_MAX_LINES",
    "OutputAccumulator",
    "OutputSnapshot",
]
