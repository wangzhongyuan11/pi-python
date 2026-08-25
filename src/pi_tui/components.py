"""Foundational render components for the generic TUI."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from .layout import wrap_text
from .width import visible_width


class Component(Protocol):
    def render(self, width: int) -> tuple[str, ...]: ...


def _pad(line: str, width: int) -> str:
    return line + " " * max(0, width - visible_width(line))


def _blank(width: int) -> str:
    return " " * width


class Text:
    """Multi-line word-wrapped text with horizontal and vertical padding."""

    __slots__ = ("_padding_x", "_padding_y", "_text")

    def __init__(self, text: str = "", *, padding_x: int = 1, padding_y: int = 1) -> None:
        self._text = text
        self._padding_x = padding_x
        self._padding_y = padding_y

    def set_text(self, text: str) -> None:
        self._text = text

    def render(self, width: int) -> tuple[str, ...]:
        if not self._text.strip():
            return ()
        content_width = max(1, width - self._padding_x * 2)
        margin = " " * self._padding_x
        body = tuple(
            _pad(f"{margin}{line}{margin}", width) for line in wrap_text(self._text, content_width)
        )
        edge = (_blank(width),) * self._padding_y
        return (*edge, *body, *edge)


class VStack:
    """Vertical stack of children with optional blank-line gaps."""

    __slots__ = ("_children", "_gap")

    def __init__(self, *children: Component, gap: int = 0) -> None:
        self._children: list[Component] = list(children)
        self._gap = gap

    def add(self, child: Component) -> None:
        self._children.append(child)

    def render(self, width: int) -> tuple[str, ...]:
        fragments: list[str] = []
        for index, child in enumerate(self._children):
            if index:
                fragments.extend([""] * self._gap)
            fragments.extend(child.render(width))
        return tuple(fragments)


class HStack:
    """Horizontal stack splitting the width into equal child columns."""

    __slots__ = ("_children", "_gap")

    def __init__(self, *children: Component, gap: int = 1) -> None:
        self._children: list[Component] = list(children)
        self._gap = gap

    def add(self, child: Component) -> None:
        self._children.append(child)

    def render(self, width: int) -> tuple[str, ...]:
        count = len(self._children)
        if count == 0:
            return ()
        share = max(1, (width - self._gap * (count - 1)) // count)
        rendered: list[tuple[str, ...]] = [child.render(share) for child in self._children]
        height = max((len(rows) for rows in rendered), default=0)
        separator = " " * self._gap
        lines: list[str] = []
        for row_index in range(height):
            cells: list[str] = [
                _pad(rows[row_index], share) if row_index < len(rows) else _blank(share)
                for rows in rendered
            ]
            lines.append(separator.join(cells))
        return tuple(lines)


class Box:
    """Padding container stacking children inside horizontal/vertical margins."""

    __slots__ = ("_children", "_padding_x", "_padding_y")

    def __init__(
        self,
        *children: Component,
        padding_x: int = 1,
        padding_y: int = 1,
    ) -> None:
        self._children: list[Component] = list(children)
        self._padding_x = padding_x
        self._padding_y = padding_y

    def add(self, child: Component) -> None:
        self._children.append(child)

    def render(self, width: int) -> tuple[str, ...]:
        inner_width = max(1, width - self._padding_x * 2)
        margin = " " * self._padding_x
        fragments: list[str] = []
        for child in self._children:
            fragments.extend(child.render(inner_width))
        body = tuple(_pad(f"{margin}{line}{margin}", width) for line in fragments)
        edge = (_blank(width),) * self._padding_y
        return (*edge, *body, *edge)


class Status:
    """Single status line truncated to the available width."""

    __slots__ = ("_text",)

    def __init__(self, text: str = "") -> None:
        self._text = text

    def set_text(self, text: str) -> None:
        self._text = text

    def render(self, width: int) -> tuple[str, ...]:
        return (_pad(self._text[:width], width),)


def render_lines(component: Component, width: int) -> Sequence[str]:
    return component.render(width)


__all__ = ["Box", "Component", "HStack", "Status", "Text", "VStack", "render_lines"]
