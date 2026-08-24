"""Bracketed-paste parsing for streamed terminal input."""

from __future__ import annotations

_START = "\x1b[200~"
_END = "\x1b[201~"


class BracketedPasteParser:
    """Splits raw input chunks into immediate keys and completed pastes."""

    __slots__ = ("_buffer", "_in_paste")

    def __init__(self) -> None:
        self._buffer = ""
        self._in_paste = False

    @property
    def in_progress(self) -> bool:
        return self._in_paste

    def feed(self, chunk: str) -> tuple[str, tuple[str, ...]]:
        self._buffer += chunk
        immediate: list[str] = []
        pastes: list[str] = []
        while self._buffer:
            if self._in_paste:
                end_index = self._buffer.find(_END)
                if end_index == -1:
                    # Partial payload: keep buffering until the terminator arrives.
                    break
                pastes.append(self._buffer[:end_index])
                self._buffer = self._buffer[end_index + len(_END) :]
                self._in_paste = False
                continue
            start_index = self._buffer.find(_START)
            if start_index == -1:
                hold = _partial_suffix_length(self._buffer, _START)
                if hold:
                    immediate.append(self._buffer[:-hold])
                    self._buffer = self._buffer[-hold:]
                else:
                    immediate.append(self._buffer)
                    self._buffer = ""
                break
            if start_index:
                immediate.append(self._buffer[:start_index])
            self._buffer = self._buffer[start_index + len(_START) :]
            self._in_paste = True
        return ("".join(immediate), tuple(pastes))


def _partial_suffix_length(buffer: str, marker: str) -> int:
    """Length of a trailing fragment that may be an incomplete ``marker``."""
    for size in range(min(len(marker) - 1, len(buffer)), 0, -1):
        if marker.startswith(buffer[-size:]):
            return size
    return 0


__all__ = ["BracketedPasteParser"]
