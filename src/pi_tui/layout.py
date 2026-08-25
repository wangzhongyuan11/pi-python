"""Text layout primitives shared by the generic TUI components."""

from __future__ import annotations

from .width import sanitize_terminal_text, truncate_to_width, visible_width


def wrap_text(text: str, width: int) -> tuple[str, ...]:
    """Greedy word wrap; words longer than ``width`` are hard-broken."""
    if width < 1:
        return ()
    normalized = sanitize_terminal_text(text).replace("\t", "   ")
    lines: list[str] = []
    for paragraph in normalized.splitlines():
        current = ""
        for word in paragraph.split(" "):
            while visible_width(word) > width:
                if current:
                    lines.append(current)
                    current = ""
                prefix = truncate_to_width(word, width)
                lines.append(prefix)
                word = word[len(prefix) :]
            if not word:
                continue
            candidate = f"{current} {word}" if current else word
            if visible_width(candidate) <= width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
    return tuple(lines)


__all__ = ["wrap_text"]
