from __future__ import annotations

from pathlib import Path

import pytest

from pi_tui.actions import TUI_ACTIONS
from pi_tui.keybindings import KeybindingRegistry

DOCS = Path(__file__).resolve().parents[2] / "docs" / "compatibility" / "tui-keys.md"


def test_registry_exposes_every_documented_action_with_upstream_defaults() -> None:
    registry = KeybindingRegistry()

    assert registry.keys_for("tui.editor.cursorLeft") == ("left", "ctrl+b")
    assert registry.keys_for("tui.input.submit") == ("enter",)
    assert registry.keys_for("tui.select.cancel") == ("escape", "ctrl+c")
    assert registry.keys_for("tui.editor.historyPrevious") == ()
    assert set(TUI_ACTIONS) == set(registry.actions())


def test_override_replaces_binding_and_reverse_lookup_follows() -> None:
    registry = KeybindingRegistry()
    registry.set_keys("tui.editor.cursorLeft", "ctrl+left")

    assert registry.keys_for("tui.editor.cursorLeft") == ("ctrl+left",)
    assert "tui.editor.cursorLeft" in registry.actions_for("ctrl+left")
    assert "tui.editor.cursorLeft" not in registry.actions_for("left")


def test_unknown_action_is_rejected() -> None:
    registry = KeybindingRegistry()

    with pytest.raises(KeyError):
        registry.keys_for("tui.editor.nonexistent")
    with pytest.raises(KeyError):
        registry.set_keys("tui.editor.nonexistent", "x")


def test_shared_keys_map_to_multiple_actions() -> None:
    registry = KeybindingRegistry()

    actions = registry.actions_for("enter")
    assert "tui.input.submit" in actions
    assert "tui.select.confirm" in actions


def test_every_action_has_description_and_doc_entry() -> None:
    assert all(definition.description for definition in TUI_ACTIONS.values())
    document = DOCS.read_text(encoding="utf-8")
    for action in TUI_ACTIONS:
        assert action in document, f"{action} missing from tui-keys.md"
