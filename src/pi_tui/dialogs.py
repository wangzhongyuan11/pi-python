"""Modal dialog primitives: selection lists and titled dialogs."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class Component(Protocol):
    def render(self, width: int) -> tuple[str, ...]: ...


def _pad(line: str, width: int) -> str:
    return line[:width].ljust(width)


class SelectList:
    """Vertical item selector with clamped navigation and confirm."""

    __slots__ = ("_items", "_selected")

    def __init__(self, items: Sequence[str], selected: int = 0) -> None:
        self._items = tuple(items)
        self._selected = min(max(selected, 0), max(0, len(self._items) - 1))

    @property
    def selected_index(self) -> int:
        return self._selected

    @property
    def selected_item(self) -> str | None:
        if not self._items:
            return None
        return self._items[self._selected]

    def down(self) -> None:
        if self._items:
            self._selected = min(self._selected + 1, len(self._items) - 1)

    def up(self) -> None:
        if self._items:
            self._selected = max(self._selected - 1, 0)

    def confirm(self) -> str | None:
        return self.selected_item


class Dialog:
    """Titled modal container holding one body component."""

    __slots__ = ("_body", "_title", "active")

    def __init__(self, title: str, body: Component | None = None) -> None:
        self._title = title
        self._body = body
        self.active = True

    @property
    def title(self) -> str:
        return self._title

    def render(self, width: int) -> tuple[str, ...]:
        lines = [_pad(self._title, width)]
        if self._body is not None:
            lines.extend(self._body.render(width))
        return tuple(lines)

    def cancel(self) -> None:
        self.active = False


__all__ = ["Dialog", "SelectList"]
