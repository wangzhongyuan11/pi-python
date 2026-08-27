"""Screen diffing renderer: full repaints on resize, dirty-line updates otherwise."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class _RendererTerminal(Protocol):
    def write(self, data: str) -> None: ...

    def move_by(self, lines: int) -> None: ...

    def clear_line(self) -> None: ...

    def clear_screen(self) -> None: ...

    @property
    def columns(self) -> int: ...


class ScreenRenderer:
    """Emits only changed lines; repaints everything when width changes."""

    __slots__ = ("_columns", "_lines", "_terminal")

    def __init__(self, terminal: _RendererTerminal) -> None:
        self._terminal = terminal
        self._lines: list[str] = []
        self._columns: int | None = None

    @property
    def line_count(self) -> int:
        return len(self._lines)

    def invalidate(self) -> None:
        self._columns = None

    def commit(self) -> None:
        """Freeze the rendered region; the next render starts on a fresh line below."""

        if self._lines:
            self._terminal.move_by(1)
        self._lines = []

    def render(self, lines: Sequence[str]) -> None:
        width = self._terminal.columns
        if self._columns != width:
            self._repaint_all(lines)
            self._columns = width
            return
        self._repaint_changed(lines)

    def _repaint_all(self, lines: Sequence[str]) -> None:
        self._terminal.clear_screen()
        if lines:
            self._terminal.write("\r\n".join(lines))
        self._lines = list(lines)

    def _repaint_changed(self, lines: Sequence[str]) -> None:
        previous = self._lines
        height = max(len(previous), len(lines))
        cursor_row = len(previous) - 1
        for index in range(height):
            new_line = lines[index] if index < len(lines) else ""
            old_line = previous[index] if index < len(previous) else None
            if new_line == old_line:
                continue
            delta = index - cursor_row
            if delta:
                self._terminal.move_by(delta)
                cursor_row = index
            self._terminal.clear_line()
            self._terminal.write(new_line)
        bottom = height - 1
        if bottom > cursor_row:
            self._terminal.move_by(bottom - cursor_row)
        self._lines = list(lines)


class InlineRenderer:
    """Append growing blocks to terminal scrollback while revising only the live tail."""

    __slots__ = ("_lines", "_terminal")

    def __init__(self, terminal: _RendererTerminal) -> None:
        self._terminal = terminal
        self._lines: list[str] = []

    def render(self, lines: Sequence[str]) -> None:
        current = list(lines)
        if current == self._lines:
            return
        if not self._lines:
            if current:
                self._write_lines(current)
            self._lines = current
            return

        shared = 0
        for old_line, new_line in zip(self._lines, current, strict=False):
            if old_line != new_line:
                break
            shared += 1

        tail = len(self._lines) - 1
        if shared < tail:
            self.commit()
            if current:
                self._write_lines(current)
        elif shared == len(self._lines):
            self._terminal.write("\r\n")
            self._write_lines(current[shared:])
        else:
            self._terminal.clear_line()
            self._write_lines(current[tail:])
        self._lines = current

    def _write_lines(self, lines: Sequence[str]) -> None:
        self._terminal.write("\r\n".join(line.rstrip(" ") for line in lines))

    def commit(self) -> None:
        """Finish the block with a real newline so the terminal can scroll naturally."""

        if self._lines:
            self._terminal.write("\r\n")
        self._lines = []


__all__ = ["InlineRenderer", "ScreenRenderer"]
