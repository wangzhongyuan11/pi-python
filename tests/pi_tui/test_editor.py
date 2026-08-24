from __future__ import annotations

from pi_tui.editor import Editor
from pi_tui.history import InputHistory


def test_editor_edits_unicode_text_and_moves_by_characters() -> None:
    editor = Editor()

    editor.insert("你好")
    assert editor.text == "你好"
    assert editor.cursor == 2

    editor.left()
    editor.insert("!")
    assert editor.text == "你!好"
    assert editor.cursor == 2

    editor.home()
    assert editor.cursor == 0
    editor.end()
    assert editor.cursor == 3


def test_editor_backspace_delete_undo_and_redo() -> None:
    editor = Editor()
    editor.insert("abc")

    editor.backspace()
    assert editor.text == "ab"

    editor.undo()
    assert editor.text == "abc"

    editor.redo()
    assert editor.text == "ab"


def test_history_navigates_older_and_newer_with_bounds() -> None:
    history = InputHistory()
    history.append("first")
    history.append("second")

    assert history.older() == "second"
    assert history.older() == "first"
    assert history.older() is None
    assert history.newer() == "second"
    assert history.newer() is None

    history.append("third")
    assert history.older() == "third"


def test_editor_submit_records_history_and_up_down_restores_draft() -> None:
    editor = Editor()

    editor.insert("hello")
    assert editor.submit() == "hello"
    assert editor.text == ""

    editor.insert("draft")
    editor.up_arrow()
    assert editor.text == "hello"
    editor.down_arrow()
    assert editor.text == "draft"

    editor.submit()
    editor.up_arrow()
    assert editor.text == "draft"
