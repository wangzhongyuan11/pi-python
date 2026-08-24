from __future__ import annotations

import threading
import time

from pi_tui.terminal import PromptToolkitTerminal
from pi_tui.testing import MemoryTerminal


class _FakeInput:
    def __init__(self) -> None:
        self._chunks: list[str] = []
        self._event = threading.Event()
        self.closed = False

    def feed(self, data: str) -> None:
        self._chunks.append(data)
        self._event.set()

    def read(self) -> str:
        while not self._event.wait(timeout=0.05):
            if self.closed:
                return ""
        self._event.clear()
        return self._chunks.pop(0)

    def close(self) -> None:
        self.closed = True
        self._event.set()


class _FakeOutput:
    def __init__(self, columns: int = 100, rows: int = 30) -> None:
        self.raw: list[str] = []
        self.flushed = 0
        self._size = (columns, rows)

    def write_raw(self, data: str) -> None:
        self.raw.append(data)

    def flush(self) -> None:
        self.flushed += 1

    def get_size(self) -> tuple[int, int]:
        return self._size


def test_memory_terminal_records_writes_and_dispatches_fed_input() -> None:
    terminal = MemoryTerminal()
    received: list[str] = []
    resized: list[bool] = []

    terminal.start(received.append, lambda: resized.append(True))
    terminal.write("hello")
    terminal.feed("typed")
    terminal.resize(columns=120, rows=40)
    terminal.move_by(-3)

    assert terminal.output == ["hello", "\x1b[3A"]
    assert received == ["typed"]
    assert resized == [True]
    assert (terminal.columns, terminal.rows) == (120, 40)


def test_memory_terminal_stop_cleans_up_dispatch_and_cursor() -> None:
    terminal = MemoryTerminal()
    received: list[str] = []

    terminal.start(received.append, lambda: None)
    terminal.hide_cursor()
    terminal.stop()
    terminal.feed("late")
    terminal.write("late")

    assert received == []
    assert terminal.output == ["\x1b[?25l"]
    assert terminal.cursor_visible is True


def test_prompt_toolkit_terminal_maps_operations_to_ansi_sequences() -> None:
    tui_input = _FakeInput()
    output = _FakeOutput(columns=100, rows=30)
    terminal = PromptToolkitTerminal(tui_input=tui_input, output=output)

    terminal.write("text")
    terminal.move_by(4)
    terminal.move_by(-2)
    terminal.hide_cursor()
    terminal.show_cursor()
    terminal.clear_line()
    terminal.clear_from_cursor()
    terminal.clear_screen()
    terminal.set_title("pi")

    assert output.raw == [
        "text",
        "\x1b[4B",
        "\x1b[2A",
        "\x1b[?25l",
        "\x1b[?25h",
        "\x1b[K",
        "\x1b[J",
        "\x1b[2J\x1b[H",
        "\x1b]0;pi\x07",
    ]
    assert (terminal.columns, terminal.rows) == (100, 30)


def test_prompt_toolkit_terminal_reader_dispatches_until_stopped() -> None:
    tui_input = _FakeInput()
    output = _FakeOutput()
    terminal = PromptToolkitTerminal(tui_input=tui_input, output=output)
    received: list[str] = []
    started = threading.Event()

    def on_input(data: str) -> None:
        received.append(data)
        started.set()

    terminal.start(on_input, lambda: None)
    tui_input.feed("abc")
    assert started.wait(timeout=2.0)
    terminal.hide_cursor()
    terminal.stop()
    tui_input.feed("after-stop")
    deadline = time.monotonic() + 0.5
    while time.monotonic() < deadline and not tui_input.closed:
        time.sleep(0.01)

    assert received == ["abc"]
    assert terminal is not None
