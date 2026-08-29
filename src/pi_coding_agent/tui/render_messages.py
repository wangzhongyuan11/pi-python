"""Agent-aware rendering of assistant message streams for the product TUI."""

from __future__ import annotations

from collections.abc import Sequence

from pi_agent import AgentMessage
from pi_ai import AssistantMessage, TextContent, ThinkingContent, ToolResultMessage, UserMessage
from pi_tui.layout import wrap_text
from pi_tui.width import sanitize_terminal_text, truncate_to_width, visible_width


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


def render_replay_lines(messages: Sequence[AgentMessage], width: int) -> tuple[str, ...]:
    """Render persisted session messages as settled transcript lines.

    Used when the product TUI opens, resumes, or switches to a session so the
    restored history is visible instead of starting from a blank prompt.
    """

    lines: list[str] = []
    for message in messages:
        if isinstance(message, UserMessage):
            for block in message.content:
                text = block.text if isinstance(block, TextContent) else "[image]"
                if not text:
                    continue
                for chunk in wrap_text(text, max(1, width - 2)):
                    lines.append(_pad(f"> {chunk}", width))
        elif isinstance(message, AssistantMessage):
            view = AssistantMessageView()
            for block in message.content:
                if isinstance(block, ThinkingContent):
                    view.add_thinking_delta(block.thinking)
                elif isinstance(block, TextContent):
                    view.add_text_delta(block.text)
            if message.stop_reason in ("error", "aborted"):
                view.fail(message.error_message or "provider error")
            lines.extend(view.render(width))
        elif isinstance(message, ToolResultMessage):
            status = "failed" if message.is_error else "done"
            detail = ""
            for block in message.content:
                if isinstance(block, TextContent) and block.text.strip():
                    detail = sanitize_terminal_text(block.text.strip().splitlines()[0])
                    break
            if detail:
                detail = f" ({truncate_to_width(detail, min(width, 120))})"
            lines.append(_pad(f"{message.tool_name}: {status}{detail}", width))
    return tuple(lines)


__all__ = ["AssistantMessageView", "render_replay_lines"]
