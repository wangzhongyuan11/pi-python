"""Frozen coding-agent action names, default keys, and legacy-name migration."""

from __future__ import annotations

import sys
from collections.abc import Mapping

from pi_tui.actions import TUI_ACTIONS, ActionDefinition


def _action(description: str, *keys: str) -> ActionDefinition:
    return ActionDefinition(default_keys=keys, description=description)


APP_ACTIONS: dict[str, ActionDefinition] = {
    "app.interrupt": _action("Cancel or abort", "escape"),
    "app.clear": _action("Clear editor", "ctrl+c"),
    "app.exit": _action("Exit when editor is empty", "ctrl+d"),
    "app.suspend": _action(
        "Suspend to background", *(() if sys.platform == "win32" else ("ctrl+z",))
    ),
    "app.thinking.cycle": _action("Cycle thinking level", "shift+tab"),
    "app.model.cycleForward": _action("Cycle to next model", "ctrl+p"),
    "app.model.cycleBackward": _action("Cycle to previous model", "shift+ctrl+p"),
    "app.model.select": _action("Open model selector", "ctrl+l"),
    "app.tools.expand": _action("Toggle tool output", "ctrl+o"),
    "app.thinking.toggle": _action("Toggle thinking blocks", "ctrl+t"),
    "app.session.toggleNamedFilter": _action("Toggle named session filter", "ctrl+n"),
    "app.editor.external": _action("Open external editor", "ctrl+g"),
    "app.message.copy": _action("Copy message to clipboard", "ctrl+x"),
    "app.message.followUp": _action("Queue follow-up message", "alt+enter"),
    "app.message.dequeue": _action("Restore queued messages", "alt+up"),
    "app.clipboard.pasteImage": _action(
        "Paste image from clipboard", "alt+v" if sys.platform == "win32" else "ctrl+v"
    ),
    "app.session.new": _action("Start a new session"),
    "app.session.tree": _action("Open session tree"),
    "app.session.fork": _action("Fork current session"),
    "app.session.resume": _action("Resume a session"),
    "app.tree.foldOrUp": _action("Fold tree branch or move up", "ctrl+left", "alt+left"),
    "app.tree.unfoldOrDown": _action("Unfold tree branch or move down", "ctrl+right", "alt+right"),
    "app.tree.editLabel": _action("Edit tree label", "shift+l"),
    "app.tree.toggleLabelTimestamp": _action("Toggle tree label timestamps", "shift+t"),
    "app.session.togglePath": _action("Toggle session path display", "ctrl+p"),
    "app.session.toggleSort": _action("Toggle session sort mode", "ctrl+s"),
    "app.session.rename": _action("Rename session", "ctrl+r"),
    "app.session.delete": _action("Delete session", "ctrl+d"),
    "app.session.deleteNoninvasive": _action(
        "Delete session when query is empty", "ctrl+backspace"
    ),
    "app.models.save": _action("Save model selection", "ctrl+s"),
    "app.models.enableAll": _action("Enable all models", "ctrl+a"),
    "app.models.clearAll": _action("Clear all models", "ctrl+x"),
    "app.models.toggleProvider": _action("Toggle all models for provider", "ctrl+p"),
    "app.models.reorderUp": _action("Move model up in order", "alt+up"),
    "app.models.reorderDown": _action("Move model down in order", "alt+down"),
    "app.tree.filter.default": _action("Tree filter: default view", "ctrl+d"),
    "app.tree.filter.noTools": _action("Tree filter: hide tool results", "ctrl+t"),
    "app.tree.filter.userOnly": _action("Tree filter: user messages only", "ctrl+u"),
    "app.tree.filter.labeledOnly": _action("Tree filter: labeled entries only", "ctrl+l"),
    "app.tree.filter.all": _action("Tree filter: show all entries", "ctrl+a"),
    "app.tree.filter.cycleForward": _action("Tree filter: cycle forward", "ctrl+o"),
    "app.tree.filter.cycleBackward": _action("Tree filter: cycle backward", "shift+ctrl+o"),
}

_LEGACY_NAMES = {
    "cursorUp": "tui.editor.cursorUp",
    "cursorDown": "tui.editor.cursorDown",
    "cursorLeft": "tui.editor.cursorLeft",
    "cursorRight": "tui.editor.cursorRight",
    "cursorWordLeft": "tui.editor.cursorWordLeft",
    "cursorWordRight": "tui.editor.cursorWordRight",
    "cursorLineStart": "tui.editor.cursorLineStart",
    "cursorLineEnd": "tui.editor.cursorLineEnd",
    "jumpForward": "tui.editor.jumpForward",
    "jumpBackward": "tui.editor.jumpBackward",
    "pageUp": "tui.editor.pageUp",
    "pageDown": "tui.editor.pageDown",
    "deleteCharBackward": "tui.editor.deleteCharBackward",
    "deleteCharForward": "tui.editor.deleteCharForward",
    "deleteWordBackward": "tui.editor.deleteWordBackward",
    "deleteWordForward": "tui.editor.deleteWordForward",
    "deleteToLineStart": "tui.editor.deleteToLineStart",
    "deleteToLineEnd": "tui.editor.deleteToLineEnd",
    "yank": "tui.editor.yank",
    "yankPop": "tui.editor.yankPop",
    "undo": "tui.editor.undo",
    "newLine": "tui.input.newLine",
    "submit": "tui.input.submit",
    "tab": "tui.input.tab",
    "copy": "tui.input.copy",
    "selectUp": "tui.select.up",
    "selectDown": "tui.select.down",
    "selectPageUp": "tui.select.pageUp",
    "selectPageDown": "tui.select.pageDown",
    "selectConfirm": "tui.select.confirm",
    "selectCancel": "tui.select.cancel",
    "interrupt": "app.interrupt",
    "clear": "app.clear",
    "exit": "app.exit",
    "suspend": "app.suspend",
    "cycleThinkingLevel": "app.thinking.cycle",
    "cycleModelForward": "app.model.cycleForward",
    "cycleModelBackward": "app.model.cycleBackward",
    "selectModel": "app.model.select",
    "expandTools": "app.tools.expand",
    "toggleThinking": "app.thinking.toggle",
    "toggleSessionNamedFilter": "app.session.toggleNamedFilter",
    "externalEditor": "app.editor.external",
    "followUp": "app.message.followUp",
    "dequeue": "app.message.dequeue",
    "pasteImage": "app.clipboard.pasteImage",
    "newSession": "app.session.new",
    "tree": "app.session.tree",
    "fork": "app.session.fork",
    "resume": "app.session.resume",
    "treeFoldOrUp": "app.tree.foldOrUp",
    "treeUnfoldOrDown": "app.tree.unfoldOrDown",
    "treeEditLabel": "app.tree.editLabel",
    "treeToggleLabelTimestamp": "app.tree.toggleLabelTimestamp",
    "toggleSessionPath": "app.session.togglePath",
    "toggleSessionSort": "app.session.toggleSort",
    "renameSession": "app.session.rename",
    "deleteSession": "app.session.delete",
    "deleteSessionNoninvasive": "app.session.deleteNoninvasive",
}


def migrate_keybindings(raw: Mapping[str, object]) -> tuple[dict[str, object], bool]:
    """Migrate legacy names; an explicitly namespaced value always wins."""

    migrated: dict[str, object] = {}
    changed = False
    for name, value in raw.items():
        canonical = _LEGACY_NAMES.get(name, name)
        changed |= canonical != name
        if canonical != name and canonical in raw:
            continue
        migrated[canonical] = value
    ordered: dict[str, object] = {}
    for name in (*TUI_ACTIONS, *APP_ACTIONS):
        if name in migrated:
            ordered[name] = migrated[name]
    for name in sorted(migrated.keys() - ordered.keys()):
        ordered[name] = migrated[name]
    return ordered, changed


__all__ = ["APP_ACTIONS", "migrate_keybindings"]
