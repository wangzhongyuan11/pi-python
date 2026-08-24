"""Reusable line editor backed by a prompt_toolkit buffer."""

from __future__ import annotations

from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document

from .history import InputHistory


class Editor:
    """Text editing state with unicode-safe cursor ops, undo, and input history."""

    __slots__ = ("_buffer", "_draft", "_history", "_redo", "_undo")

    def __init__(self, *, multiline: bool = False, history: InputHistory | None = None) -> None:
        self._buffer = Buffer(multiline=multiline)
        self._history = history if history is not None else InputHistory()
        self._draft: str | None = None
        self._undo: list[tuple[str, int]] = []
        self._redo: list[tuple[str, int]] = []

    @property
    def text(self) -> str:
        return self._buffer.text

    @property
    def cursor(self) -> int:
        return self._buffer.cursor_position

    def insert(self, data: str) -> None:
        self._checkpoint()
        self._buffer.insert_text(data)

    def backspace(self) -> None:
        if self._buffer.cursor_position > 0:
            self._checkpoint()
            self._buffer.cursor_left()
            self._buffer.delete()

    def delete(self) -> None:
        if self._buffer.cursor_position < len(self._buffer.text):
            self._checkpoint()
            self._buffer.delete()

    def left(self) -> None:
        self._buffer.cursor_left()

    def right(self) -> None:
        self._buffer.cursor_right()

    def home(self) -> None:
        self._buffer.cursor_position = 0

    def end(self) -> None:
        self._buffer.cursor_position = len(self._buffer.text)

    def undo(self) -> None:
        if not self._undo:
            return
        self._redo.append(self._state())
        text, position = self._undo.pop()
        self._apply(text, position)

    def redo(self) -> None:
        if not self._redo:
            return
        self._undo.append(self._state())
        text, position = self._redo.pop()
        self._apply(text, position)

    def set_text(self, value: str) -> None:
        self._checkpoint()
        self._apply(value, min(self._buffer.cursor_position, len(value)))

    def submit(self) -> str:
        value = self._buffer.text
        self._history.append(value)
        self._draft = None
        self._undo.clear()
        self._redo.clear()
        self._apply("", 0)
        return value

    def up_arrow(self) -> None:
        entry = self._history.older()
        if entry is None:
            return
        if self._draft is None:
            self._draft = self._buffer.text
        self._apply(entry, len(entry))

    def down_arrow(self) -> None:
        entry = self._history.newer()
        if entry is None:
            if self._draft is not None:
                restored = self._draft
                self._draft = None
                self._apply(restored, len(restored))
            return
        self._apply(entry, len(entry))

    def _state(self) -> tuple[str, int]:
        return (self._buffer.text, self._buffer.cursor_position)

    def _checkpoint(self) -> None:
        self._undo.append(self._state())
        self._redo.clear()

    def _apply(self, text: str, position: int) -> None:
        self._buffer.document = Document(text, position)


__all__ = ["Editor"]
