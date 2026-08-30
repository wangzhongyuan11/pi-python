"""Submitted-input history with bounded, cursor-based navigation."""

from __future__ import annotations


class InputHistory:
    """Stores submitted entries; navigation clamps at both ends."""

    __slots__ = ("_entries", "_index")

    def __init__(self) -> None:
        self._entries: list[str] = []
        self._index = 0

    def append(self, entry: str) -> None:
        if not entry:
            return
        if not self._entries or self._entries[-1] != entry:
            self._entries.append(entry)
        self._index = len(self._entries)

    def older(self) -> str | None:
        if self._index == 0:
            return None
        self._index -= 1
        return self._entries[self._index]

    def newer(self) -> str | None:
        if self._index >= len(self._entries):
            return None
        self._index += 1
        if self._index == len(self._entries):
            return None
        return self._entries[self._index]

    def reset(self) -> None:
        self._index = len(self._entries)


__all__ = ["InputHistory"]
