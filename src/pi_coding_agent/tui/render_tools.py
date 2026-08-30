"""In-place tool execution rows for the interactive product TUI."""

from __future__ import annotations

from typing import cast

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

    def update(self, detail: str | None = None) -> None:
        if self._state == _STATE_RUNNING:
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


def edit_diff_summary(details: object) -> str | None:
    """Compact ``+N -M, line K`` summary from edit tool result details."""
    if not isinstance(details, dict):
        return None
    payload = cast("dict[str, object]", details)
    diff = payload.get("diff")
    if not isinstance(diff, str):
        return None
    added = sum(1 for line in diff.split("\n") if line.startswith("+"))
    removed = sum(1 for line in diff.split("\n") if line.startswith("-"))
    replacements = payload.get("replacements")
    blocks = (
        replacements if isinstance(replacements, int) and not isinstance(replacements, bool) else 0
    )
    parts = [f"{blocks} block(s)", f"+{added} -{removed}"]
    first_changed_line = payload.get("firstChangedLine")
    if isinstance(first_changed_line, int) and not isinstance(first_changed_line, bool):
        parts.append(f"line {first_changed_line}")
    return ", ".join(parts)


__all__ = ["ToolExecutionView", "edit_diff_summary"]
