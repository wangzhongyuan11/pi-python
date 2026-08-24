"""Overlay stack routing input to the topmost modal dialog."""

from __future__ import annotations

from .dialogs import Dialog


class OverlayStack:
    """Last-in-first-out modal container; Escape cancels only the top dialog."""

    __slots__ = ("_stack",)

    def __init__(self) -> None:
        self._stack: list[Dialog] = []

    @property
    def top(self) -> Dialog | None:
        return self._stack[-1] if self._stack else None

    def push(self, dialog: Dialog) -> None:
        self._stack.append(dialog)

    def pop(self) -> Dialog | None:
        return self._stack.pop() if self._stack else None

    def handle_escape(self) -> Dialog | None:
        if not self._stack:
            return None
        dialog = self._stack.pop()
        dialog.cancel()
        return dialog


__all__ = ["OverlayStack"]
