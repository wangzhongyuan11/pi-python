from __future__ import annotations

import pytest

from pi_tui.width import (
    pad_to_width,
    sanitize_terminal_text,
    truncate_to_width,
    visible_width,
)


def test_ascii_counts_one_cell_per_character() -> None:
    assert visible_width("hello") == 5
    assert visible_width("") == 0


def test_wide_characters_count_two_cells() -> None:
    assert visible_width("中文") == 4
    assert visible_width("中文abc") == 7


def test_combining_marks_add_zero_cells() -> None:
    assert visible_width("é") == 1
    assert visible_width("́") == 0


def test_tabs_expand_to_three_cells() -> None:
    assert visible_width("\ta") == 4


def test_ansi_escape_sequences_are_invisible() -> None:
    assert visible_width("\x1b[31mred\x1b[0m") == 3
    assert visible_width("\x1b[2J\x1b[Hx") == 1


def test_presentation_emoji_counts_two_cells() -> None:
    assert visible_width("\U0001f44d") == 2


def test_truncate_keeps_within_cell_budget_without_splitting_wide_chars() -> None:
    assert truncate_to_width("abcdef", 6) == "abcdef"
    assert truncate_to_width("abcdef", 4) == "abcd"
    assert truncate_to_width("中文abc", 5) == "中文a"
    assert truncate_to_width("中文", 3) == "中"
    assert truncate_to_width("\x1b[31mred\x1b[0m", 2) == "re"


def test_pad_reaches_exact_visible_width() -> None:
    assert pad_to_width("ab", 5) == "ab   "
    assert pad_to_width("中文", 5) == "中文 "
    with pytest.raises(ValueError):
        pad_to_width("toolong", 3)


def test_terminal_text_sanitizer_removes_escape_and_control_sequences() -> None:
    text = "safe\x1b[2J\x1b]0;owned\x07\r\x00\nnext\tcell"

    assert sanitize_terminal_text(text) == "safe\nnext\tcell"
