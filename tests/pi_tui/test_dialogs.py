from __future__ import annotations

from pi_tui.components import Text
from pi_tui.dialogs import Dialog, SelectList
from pi_tui.overlays import OverlayStack
from pi_tui.width import visible_width


def test_select_list_navigation_clamps_and_confirms_selected_item() -> None:
    selector = SelectList(("alpha", "beta", "gamma"))

    assert selector.selected_index == 0
    selector.down()
    assert selector.selected_item == "beta"
    selector.down()
    selector.down()
    assert selector.selected_index == 2
    selector.down()
    assert selector.selected_index == 2

    selector.up()
    assert selector.selected_item == "beta"
    selector.up()
    selector.up()
    selector.up()
    assert selector.selected_index == 0

    assert selector.confirm() == "alpha"


def test_select_list_without_items_confirms_none() -> None:
    assert SelectList(()).confirm() is None


def test_dialog_renders_title_and_body_and_cancel_deactivates() -> None:
    dialog = Dialog("Confirm", Text("Sure?", padding_x=1, padding_y=0))

    lines = dialog.render(12)
    assert lines[0].strip() == "Confirm"
    assert any("Sure?" in line for line in lines)

    dialog.cancel()
    assert not dialog.active


def test_dialog_title_is_safe_and_cell_width_bounded() -> None:
    line = Dialog("中文中文\x1b]0;owned\x07").render(4)[0]

    assert line == "中文"
    assert visible_width(line) == 4
    assert "\x1b" not in line


def test_overlay_nesting_routes_to_topmost_and_escape_cancels_top_only() -> None:
    stack = OverlayStack()
    first = Dialog("first")
    second = Dialog("second")

    stack.push(first)
    stack.push(second)

    assert stack.top is second

    cancelled = stack.handle_escape()
    assert cancelled is second
    assert not second.active and first.active
    assert stack.top is first

    assert stack.handle_escape() is first
    assert stack.handle_escape() is None
    assert stack.top is None
