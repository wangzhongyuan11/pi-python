"""In-place tool execution rows for the interactive product TUI."""

from __future__ import annotations

from pi_tui.layout import wrap_text
from pi_tui.width import visible_width

_STATE_RUNNING = "running"
_STATE_DONE = "done"
_STATE_FAILED = "failed"


class ToolExecutionView:
    """One stable row per tool call; state transitions rewrite the same row."""

    __slots__ = ("_detail", "_state", "_tool")

    def __init__(self, tool_name: str) -> None:
        self._tool = tool_name
        self._state = _STATE_RUNNING
        self._detail: str | None = None

    @property
    def state(self) -> str:
        return self._state

    def complete(self, detail: str | None = None) -> None:
        self._state = _STATE_DONE
        self._detail = detail

    def fail(self, detail: str | None = None) -> None:
        self._state = _STATE_FAILED
        self._detail = detail

    def render(self, width: int) -> tuple[str, ...]:
        suffix = f" ({self._detail})" if self._detail else ""
        text = f"{self._tool}: {self._state}{suffix}"
        return tuple(_pad(line, width) for line in wrap_text(text, width))


def _pad(line: str, width: int) -> str:
    return line + " " * max(0, width - visible_width(line))


__all__ = ["ToolExecutionView"]
