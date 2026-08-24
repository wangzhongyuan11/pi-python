from __future__ import annotations

from pi_tui.autocomplete import Autocompleter
from pi_tui.editor import Editor
from pi_tui.paste import BracketedPasteParser


class _TableProvider:
    def __init__(self, table: dict[str, tuple[str, ...]]) -> None:
        self._table = table

    def completions(self, prefix: str) -> tuple[str, ...]:
        return self._table.get(prefix, ())


def test_bracketed_paste_parser_separates_plain_keys_from_pastures() -> None:
    parser = BracketedPasteParser()

    assert parser.feed("abc") == ("abc", ())
    assert parser.feed("\x1b[200~pasted\x1b[201~") == ("", ("pasted",))
    assert parser.feed("done") == ("done", ())
    assert not parser.in_progress


def test_bracketed_paste_spanning_chunks_completes_with_payload_intact() -> None:
    parser = BracketedPasteParser()

    assert parser.feed("pre \x1b[200~he") == ("pre ", ())
    assert parser.in_progress
    assert parser.feed("llo") == ("", ())
    assert parser.feed(" world\x1b[201~tail") == ("tail", ("hello world",))


def test_editor_paste_inserts_multiline_text_atomically_at_cursor() -> None:
    editor = Editor()
    editor.insert("ab")
    editor.left()

    editor.paste("X\nY")

    assert editor.text == "aX\nYb"
    assert editor.cursor == 4

    editor.undo()
    assert editor.text == "ab"


def test_autocompleter_replaces_partial_word_and_cycles_candidates() -> None:
    editor = Editor()
    editor.insert("to")
    completer = Autocompleter(
        _TableProvider({"to": ("todo.py", "todo.txt", "tools")}),
        editor,
    )

    assert completer.suggestions() == ("todo.py", "todo.txt", "tools")
    assert completer.apply_next() and editor.text == "todo.py"
    assert completer.apply_next() and editor.text == "todo.txt"
    assert completer.apply_next() and editor.text == "tools"
    assert not completer.apply_next()


def test_autocompleter_without_candidates_reports_no_match() -> None:
    editor = Editor()
    editor.insert("zzz")

    assert not Autocompleter(_TableProvider({}), editor).apply_next()
