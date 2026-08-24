"""TUI application loop state: component tree, invalidation, and repaint."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from .render import ScreenRenderer


class Component(Protocol):
    def render(self, width: int) -> tuple[str, ...]: ...


class _AppTerminal(Protocol):
    def write(self, data: str) -> None: ...

    def move_by(self, lines: int) -> None: ...

    def clear_line(self) -> None: ...

    def clear_screen(self) -> None: ...

    @property
    def columns(self) -> int: ...

    @property
    def rows(self) -> int: ...


class Application:
    """Renders one component tree; resize forces a clean full repaint."""

    __slots__ = ("_dirty", "_fullscreen", "_renderer", "_root", "_terminal")

    def __init__(
        self,
        terminal: _AppTerminal,
        root: Component | None = None,
        *,
        fullscreen: bool = False,
        renderer: ScreenRenderer | None = None,
    ) -> None:
        self._terminal = terminal
        self._root = root
        self._fullscreen = fullscreen
        self._renderer = renderer or ScreenRenderer(terminal)
        self._dirty = False

    @property
    def root(self) -> Component | None:
        return self._root

    def set_root(self, root: Component) -> None:
        self._root = root
        self.invalidate()

    def invalidate(self) -> None:
        self._dirty = True

    def handle_resize(self) -> None:
        self.invalidate()
        self.render()

    def on_terminal_resize(self) -> Callable[[], None]:
        """Returns an ``on_resize`` handler bound to this application."""

        return self.handle_resize

    def render(self) -> None:
        if self._root is None:
            return
        lines = list(self._root.render(self._terminal.columns))
        if self._fullscreen:
            rows = max(1, self._terminal.rows)
            lines = lines[-rows:]
            lines.extend([""] * (rows - len(lines)))
        if self._dirty:
            self._renderer.invalidate()
            self._dirty = False
        self._renderer.render(lines)


__all__ = ["Application"]
