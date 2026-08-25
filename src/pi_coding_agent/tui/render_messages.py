"""Agent-aware rendering of assistant message streams for the product TUI."""

from __future__ import annotations

from pi_tui.layout import wrap_text


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
            wrapped = wrap_text(f"thinking: {self._thinking.strip()}", width)
            lines.extend(wrapped[:1])
            lines.extend(" " * len("thinking: ") + chunk for chunk in wrapped[1:])
        if self._text.strip():
            lines.extend(wrap_text(self._text.strip(), width))
        if self._error is not None:
            lines.append(f"[error] {self._error}")
        return tuple(_pad(line, width) for line in lines)


def _pad(line: str, width: int) -> str:
    return line + " " * max(0, width - len(line))


__all__ = ["AssistantMessageView"]
