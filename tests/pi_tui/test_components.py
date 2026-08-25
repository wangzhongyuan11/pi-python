from __future__ import annotations

from pi_tui.components import Box, HStack, Status, Text, VStack
from pi_tui.layout import wrap_text


def test_wrap_text_breaks_on_words_and_hard_wraps_long_words() -> None:
    assert wrap_text("one two three four", 8) == ("one two", "three", "four")
    assert wrap_text("extraordinary", 5) == ("extra", "ordin", "ary")
    assert wrap_text("", 8) == ()


def test_wrap_text_uses_terminal_cells_for_wide_characters() -> None:
    assert wrap_text("中文中文", 4) == ("中文", "中文")


def test_text_renders_padded_lines_at_eighty_columns() -> None:
    text = Text("hello world", padding_x=1, padding_y=0)
    lines = text.render(80)

    assert len(lines) == 1
    assert lines[0] == " hello world" + " " * 68


def test_text_applies_vertical_padding_and_blank_text_renders_nothing() -> None:
    padded = Text("hi", padding_x=0, padding_y=2)
    assert padded.render(4) == ("    ", "    ", "hi  ", "    ", "    ")

    blank = Text("   ", padding_x=0, padding_y=1)
    assert blank.render(10) == ()


def test_vstack_stacks_children_with_gap() -> None:
    first = Text("ab", padding_x=0, padding_y=0)
    second = Text("cd", padding_x=0, padding_y=0)
    stack = VStack(first, second, gap=1)

    assert stack.render(6) == (
        "ab    ",
        "",
        "cd    ",
    )


def test_hstack_splits_width_and_joins_rows() -> None:
    first = Text("ab", padding_x=0, padding_y=0)
    second = Text("cd", padding_x=0, padding_y=0)
    stack = HStack(first, second, gap=2)

    assert stack.render(10) == ("ab" + " " * 4 + "cd  ",)


def test_box_wraps_children_in_padding() -> None:
    box = Box(Text("hi", padding_x=0, padding_y=0), padding_x=1, padding_y=1)

    assert box.render(6) == (
        "      ",
        " hi   ",
        "      ",
    )


def test_status_renders_single_truncated_line() -> None:
    assert Status("ready").render(10) == ("ready     ",)
    assert Status("overflowing-status").render(5) == ("overf",)


def test_components_truncate_wide_text_and_remove_terminal_controls() -> None:
    assert Status("中文中文").render(4) == ("中文",)
    assert Text("safe\x1b[2Jowned", padding_x=0, padding_y=0).render(20) == (
        "safeowned" + " " * 11,
    )


def test_composed_view_snapshots_at_full_and_narrow_screens() -> None:
    body = Text(
        "The quick brown fox jumps over the lazy dog again and again",
        padding_x=1,
        padding_y=0,
    )
    view = VStack(body, Status("READY"), gap=1)

    wide = view.render(80)
    assert wide[:3] == (
        " The quick brown fox jumps over the lazy dog again and again" + " " * 20,
        "",
        "READY" + " " * 75,
    )
    narrow = view.render(40)
    assert narrow[0] == " The quick brown fox jumps over the" + " " * 5
    assert narrow[-1] == "READY" + " " * 35
