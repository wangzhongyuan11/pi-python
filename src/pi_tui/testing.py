"""In-memory terminal double for deterministic TUI tests."""

from __future__ import annotations

from .terminal import InputHandler, ResizeHandler


class MemoryTerminal:
    """Records every render operation and replays fed input to handlers."""

    __slots__ = (
        "_columns",
        "_input_handler",
        "_resize_handler",
        "_rows",
        "_started",
        "cursor_visible",
        "output",
        "resized",
        "title",
    )

    def __init__(self, *, columns: int = 80, rows: int = 24) -> None:
        self.output: list[str] = []
        self.resized: list[tuple[int, int]] = []
        self.cursor_visible = True
        self.title: str | None = None
        self._columns = columns
        self._rows = rows
        self._started = False
        self._input_handler: InputHandler | None = None
        self._resize_handler: ResizeHandler | None = None

    def start(self, on_input: InputHandler, on_resize: ResizeHandler) -> None:
        self._started = True
        self._input_handler = on_input
        self._resize_handler = on_resize

    def stop(self) -> None:
        self._started = False
        self._input_handler = None
        self._resize_handler = None
        self.cursor_visible = True

    def write(self, data: str) -> None:
        if not self._started:
            return
        self.output.append(data)

    @property
    def columns(self) -> int:
        return self._columns

    @property
    def rows(self) -> int:
        return self._rows

    def feed(self, data: str) -> None:
        handler = self._input_handler
        if handler is not None:
            handler(data)

    def resize(self, *, columns: int, rows: int) -> None:
        self._columns = columns
        self._rows = rows
        self.resized.append((columns, rows))
        handler = self._resize_handler
        if handler is not None:
            handler()

    def move_by(self, lines: int) -> None:
        self.write(f"\x1b[{lines}B" if lines > 0 else f"\x1b[{-lines}A")

    def hide_cursor(self) -> None:
        self.write("\x1b[?25l")
        self.cursor_visible = False

    def show_cursor(self) -> None:
        self.write("\x1b[?25h")
        self.cursor_visible = True

    def clear_line(self) -> None:
        self.write("\x1b[K")

    def clear_from_cursor(self) -> None:
        self.write("\x1b[J")

    def clear_screen(self) -> None:
        self.write("\x1b[2J\x1b[H")

    def set_title(self, title: str) -> None:
        self.title = title


__all__ = ["MemoryTerminal"]
