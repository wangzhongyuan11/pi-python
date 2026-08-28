"""Agent-aware rendering of assistant message streams for the product TUI."""

from __future__ import annotations

from pi_tui.layout import wrap_text
from pi_tui.width import visible_width


class AssistantMessageView:
    """Accumulates text/thinking deltas and renders stable line fragments."""

    __slots__ = ("_error", "_text", "_thinking")

    def __init__(self) -> None:
        self._text = ""
        self._thinking = ""
        self._error: str | None = None

    @property
    def failed(self) -> bool:
        return self._error is not None

    def add_text_delta(self, delta: str) -> None:
        if self._error is not None:
            return
        self._text += delta

    def add_thinking_delta(self, delta: str) -> None:
        if self._error is not None:
            return
        self._thinking += delta

    def fail(self, error_message: str) -> None:
        self._error = error_message

    def render(self, width: int) -> tuple[str, ...]:
        lines: list[str] = []
        if self._thinking.strip():
            prefix = "thinking: "
            content_width = width - visible_width(prefix)
            if content_width <= 0:
                lines.extend(wrap_text(f"{prefix}{self._thinking.strip()}", width))
            else:
                wrapped = wrap_text(self._thinking.strip(), content_width)
                if wrapped:
                    lines.append(f"{prefix}{wrapped[0]}")
                    lines.extend(" " * len(prefix) + chunk for chunk in wrapped[1:])
        if self._text.strip():
            lines.extend(wrap_text(self._text.strip(), width))
        if self._error is not None:
            lines.append(f"[error] {self._error}")
        return tuple(_pad(line, width) for line in lines)


def _pad(line: str, width: int) -> str:
    return line + " " * max(0, width - visible_width(line))


__all__ = ["AssistantMessageView"]
