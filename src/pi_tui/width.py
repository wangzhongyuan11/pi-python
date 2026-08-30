"""Terminal display-width helpers aware of wide characters and escapes."""

from __future__ import annotations

from wcwidth import wcwidth


def _consume_until_st(text: str, start: int, *, bell_terminates: bool) -> int:
    index = start
    while index < len(text):
        character = text[index]
        if bell_terminates and character == "\x07":
            return index + 1
        if character == "\x9c":
            return index + 1
        if character == "\x1b" and index + 1 < len(text) and text[index + 1] == "\\":
            return index + 2
        index += 1
    return len(text)


def _without_terminal_sequences(text: str) -> str:
    result: list[str] = []
    index = 0
    while index < len(text):
        character = text[index]
        if character == "\x1b":
            index += 1
            if index >= len(text):
                break
            introducer = text[index]
            index += 1
            if introducer == "[":
                while index < len(text) and not "@" <= text[index] <= "~":
                    index += 1
                index += index < len(text)
            elif introducer == "]":
                index = _consume_until_st(text, index, bell_terminates=True)
            elif introducer in "PX^_":
                index = _consume_until_st(text, index, bell_terminates=False)
            continue
        if character == "\x9b":
            index += 1
            while index < len(text) and not "@" <= text[index] <= "~":
                index += 1
            index += index < len(text)
            continue
        if character in "\x90\x98\x9d\x9e\x9f":
            index = _consume_until_st(text, index + 1, bell_terminates=character == "\x9d")
            continue
        result.append(character)
        index += 1
    return "".join(result)


def strip_ansi(text: str) -> str:
    return _without_terminal_sequences(text)


def sanitize_terminal_text(text: str) -> str:
    """Remove terminal instructions and unsafe control characters from text."""
    clean = _without_terminal_sequences(text)
    return "".join(
        character
        for character in clean
        if character in "\n\t" or not (ord(character) < 32 or 127 <= ord(character) <= 159)
    )


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
    for character in strip_ansi(text):
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


__all__ = [
    "pad_to_width",
    "sanitize_terminal_text",
    "strip_ansi",
    "truncate_to_width",
    "visible_width",
]
