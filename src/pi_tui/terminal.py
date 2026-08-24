"""Terminal abstraction for the generic TUI, rendered through output ports."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from typing import Protocol


class TuiInput(Protocol):
    """Blocking byte-chunk source; ``read`` returns "" once closed."""

    def read(self) -> str: ...

    def close(self) -> None: ...


class TuiOutput(Protocol):
    def write_raw(self, data: str) -> None: ...

    def flush(self) -> None: ...

    def get_size(self) -> tuple[int, int]: ...


InputHandler = Callable[[str], None]
ResizeHandler = Callable[[], None]


class PromptToolkitTerminal:
    """Adapter that renders through a prompt_toolkit-style output port."""

    __slots__ = (
        "_loop",
        "_on_input",
        "_on_resize",
        "_output",
        "_reader",
        "_stopping",
        "_tui_input",
    )

    def __init__(
        self,
        *,
        tui_input: TuiInput,
        output: TuiOutput,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        self._tui_input = tui_input
        self._output = output
        self._loop = loop
        self._on_input: InputHandler | None = None
        self._on_resize: ResizeHandler | None = None
        self._reader: threading.Thread | None = None
        self._stopping = threading.Event()

    def start(self, on_input: InputHandler, on_resize: ResizeHandler) -> None:
        if self._reader is not None:
            return
        self._on_input = on_input
        self._on_resize = on_resize
        self._stopping.clear()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def stop(self) -> None:
        self._stopping.set()
        self._on_input = None
        self._tui_input.close()
        if self._reader is not None:
            self._reader.join(timeout=2.0)
            self._reader = None

    def write(self, data: str) -> None:
        self._output.write_raw(data)
        self._output.flush()

    @property
    def columns(self) -> int:
        return self._output.get_size()[0]

    @property
    def rows(self) -> int:
        return self._output.get_size()[1]

    def move_by(self, lines: int) -> None:
        if lines > 0:
            self.write(f"\x1b[{lines}B")
        elif lines < 0:
            self.write(f"\x1b[{-lines}A")

    def hide_cursor(self) -> None:
        self.write("\x1b[?25l")

    def show_cursor(self) -> None:
        self.write("\x1b[?25h")

    def clear_line(self) -> None:
        self.write("\x1b[K")

    def clear_from_cursor(self) -> None:
        self.write("\x1b[J")

    def clear_screen(self) -> None:
        self.write("\x1b[2J\x1b[H")

    def set_title(self, title: str) -> None:
        self.write(f"\x1b]0;{title}\x07")

    def _read_loop(self) -> None:
        while not self._stopping.is_set():
            try:
                data = self._tui_input.read()
            except Exception:
                break
            if not data:
                break
            handler = self._on_input
            if handler is None:
                continue
            if self._loop is not None:
                self._loop.call_soon_threadsafe(handler, data)
            else:
                handler(data)


__all__ = ["InputHandler", "PromptToolkitTerminal", "ResizeHandler", "TuiInput", "TuiOutput"]
