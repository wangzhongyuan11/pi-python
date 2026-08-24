"""Terminal display-width helpers aware of wide characters and escapes."""

from __future__ import annotations

import re

from wcwidth import wcwidth

_ANSI_ESCAPE_RE = re.compile(r"\x1b(?:\[[0-9;:?]*[A-Za-z]|\][^\x07\x1b]*(?:\x07|\x1b\\))")


def strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE_RE.sub("", text)


def visible_width(text: str, *, tab_width: int = 3) -> int:
    """Terminal cell count of ``text``; tabs expand and escapes are invisible."""
    if not text:
        return 0
    clean = strip_ansi(text.replace("\t", " " * tab_width))
    total = 0
    for character in clean:
        cells = wcwidth(character)
        total += cells if cells > 0 else 0
    return total


def truncate_to_width(text: str, width: int) -> str:
    """Longest prefix whose visible width fits exactly within ``width``."""
    result: list[str] = []
    used = 0
    for character in text:
        cells = wcwidth(character)
        cells = cells if cells > 0 else 0
        if used + cells > width:
            break
        result.append(character)
        used += cells
    return "".join(result)


def pad_to_width(text: str, width: int) -> str:
    padding = width - visible_width(text)
    if padding < 0:
        raise ValueError(f"text wider than {width} columns: {text!r}")
    return text + " " * padding


__all__ = ["pad_to_width", "strip_ansi", "truncate_to_width", "visible_width"]
