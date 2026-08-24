"""Text layout primitives shared by the generic TUI components."""

from __future__ import annotations


def wrap_text(text: str, width: int) -> tuple[str, ...]:
    """Greedy word wrap; words longer than ``width`` are hard-broken."""
    if width < 1:
        return ()
    normalized = text.replace("\t", "   ")
    lines: list[str] = []
    for paragraph in normalized.splitlines():
        current = ""
        for word in paragraph.split(" "):
            while len(word) > width:
                if current:
                    lines.append(current)
                    current = ""
                lines.append(word[:width])
                word = word[width:]
            if not word:
                continue
            candidate = f"{current} {word}" if current else word
            if len(candidate) <= width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
    return tuple(lines)


__all__ = ["wrap_text"]
