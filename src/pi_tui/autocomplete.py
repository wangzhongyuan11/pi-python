"""Word completion cycling on top of the shared editor state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .editor import Editor


class CompletionProvider(Protocol):
    def completions(self, prefix: str) -> tuple[str, ...]: ...


@dataclass(frozen=True, slots=True)
class _Cycle:
    original_text: str
    word_start: int
    word_end: int
    candidates: tuple[str, ...]
    index: int


def _current_word(editor: Editor) -> tuple[int, int]:
    position = editor.cursor
    start = position
    text = editor.text
    while start > 0 and not text[start - 1].isspace():
        start -= 1
    return (start, position)


class Autocompleter:
    """Replaces the word before the cursor with provider candidates in turn."""

    __slots__ = ("_cycle", "_editor", "_provider")

    def __init__(self, provider: CompletionProvider, editor: Editor) -> None:
        self._provider = provider
        self._editor = editor
        self._cycle: _Cycle | None = None

    def suggestions(self) -> tuple[str, ...]:
        start, end = _current_word(self._editor)
        return self._provider.completions(self._editor.text[start:end])

    def apply_next(self) -> bool:
        if self._cycle is None:
            start, end = _current_word(self._editor)
            prefix = self._editor.text[start:end]
            candidates = self._provider.completions(prefix)
            if not candidates or end != self._editor.cursor:
                return False
            self._cycle = _Cycle(
                original_text=self._editor.text,
                word_start=start,
                word_end=end,
                candidates=candidates,
                index=0,
            )
        else:
            if self._cycle.index + 1 >= len(self._cycle.candidates):
                return False
            self._cycle = _Cycle(
                original_text=self._cycle.original_text,
                word_start=self._cycle.word_start,
                word_end=self._cycle.word_end,
                candidates=self._cycle.candidates,
                index=self._cycle.index + 1,
            )
        candidate = self._cycle.candidates[self._cycle.index]
        text = (
            self._cycle.original_text[: self._cycle.word_start]
            + candidate
            + self._cycle.original_text[self._cycle.word_end :]
        )
        self._editor.set_text(text)
        self._editor.end()
        return True


__all__ = ["Autocompleter", "CompletionProvider"]
