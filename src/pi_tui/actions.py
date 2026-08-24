"""Frozen action surface and default keys for the generic TUI."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ActionDefinition:
    default_keys: tuple[str, ...]
    description: str


def _action(description: str, *keys: str) -> ActionDefinition:
    return ActionDefinition(default_keys=tuple(keys), description=description)


TUI_ACTIONS: dict[str, ActionDefinition] = {
    # Editor navigation and editing
    "tui.editor.cursorUp": _action("Move cursor up", "up"),
    "tui.editor.cursorDown": _action("Move cursor down", "down"),
    "tui.editor.historyPrevious": _action("Select previous prompt history entry"),
    "tui.editor.historyNext": _action("Select next prompt history entry"),
    "tui.editor.cursorLeft": _action("Move cursor left", "left", "ctrl+b"),
    "tui.editor.cursorRight": _action("Move cursor right", "right", "ctrl+f"),
    "tui.editor.cursorWordLeft": _action("Move cursor word left", "alt+left", "ctrl+left", "alt+b"),
    "tui.editor.cursorWordRight": _action(
        "Move cursor word right", "alt+right", "ctrl+right", "alt+f"
    ),
    "tui.editor.cursorLineStart": _action("Move to line start", "home", "ctrl+home", "ctrl+a"),
    "tui.editor.cursorLineEnd": _action("Move to line end", "end", "ctrl+end", "ctrl+e"),
    "tui.editor.jumpForward": _action("Jump forward to character", "ctrl+]"),
    "tui.editor.jumpBackward": _action("Jump backward to character", "ctrl+alt+]"),
    "tui.editor.pageUp": _action("Page up", "pageup", "ctrl+pageup"),
    "tui.editor.pageDown": _action("Page down", "pagedown", "ctrl+pagedown"),
    "tui.editor.deleteCharBackward": _action("Delete character backward", "backspace"),
    "tui.editor.deleteCharForward": _action("Delete character forward", "delete", "ctrl+d"),
    "tui.editor.deleteWordBackward": _action("Delete word backward", "ctrl+w", "alt+backspace"),
    "tui.editor.deleteWordForward": _action("Delete word forward", "alt+d", "alt+delete"),
    "tui.editor.deleteToLineStart": _action("Delete to line start", "ctrl+u"),
    "tui.editor.deleteToLineEnd": _action("Delete to line end", "ctrl+k"),
    "tui.editor.yank": _action("Yank", "ctrl+y"),
    "tui.editor.yankPop": _action("Yank pop", "alt+y"),
    "tui.editor.undo": _action("Undo", "ctrl+-"),
    # Generic input actions
    "tui.input.newLine": _action("Insert newline", "shift+enter", "ctrl+j"),
    "tui.input.submit": _action("Submit input", "enter"),
    "tui.input.tab": _action("Tab / autocomplete", "tab"),
    "tui.input.copy": _action("Copy selection", "ctrl+c"),
    # Generic selection actions
    "tui.select.up": _action("Move selection up", "up"),
    "tui.select.down": _action("Move selection down", "down"),
    "tui.select.pageUp": _action("Selection page up", "pageup"),
    "tui.select.pageDown": _action("Selection page down", "pagedown"),
    "tui.select.confirm": _action("Confirm selection", "enter"),
    "tui.select.cancel": _action("Cancel selection", "escape", "ctrl+c"),
    # Alternate-screen viewport navigation
    "tui.altScreen.pageUp": _action("Scroll viewport up one page", "pageup"),
    "tui.altScreen.pageDown": _action("Scroll viewport down one page", "pagedown"),
    "tui.altScreen.halfPageUp": _action("Scroll viewport up half a page"),
    "tui.altScreen.halfPageDown": _action("Scroll viewport down half a page"),
    "tui.altScreen.lineUp": _action("Scroll viewport up one line"),
    "tui.altScreen.lineDown": _action("Scroll viewport down one line"),
    "tui.altScreen.previousPrompt": _action("Jump to previous semantic prompt", "ctrl+shift+up"),
    "tui.altScreen.nextPrompt": _action("Jump to next semantic prompt", "ctrl+shift+down"),
    "tui.altScreen.search": _action("Search the primary scroll view", "ctrl+shift+f"),
    "tui.altScreen.searchNext": _action("Select the next search match", "enter", "ctrl+g"),
    "tui.altScreen.searchPrevious": _action(
        "Select the previous search match", "shift+enter", "ctrl+shift+g"
    ),
    "tui.altScreen.searchClose": _action("Close transcript search", "escape"),
    "tui.altScreen.top": _action("Scroll viewport to top", "home"),
    "tui.altScreen.bottom": _action("Scroll viewport to bottom", "end"),
}


__all__ = ["ActionDefinition", "TUI_ACTIONS"]
