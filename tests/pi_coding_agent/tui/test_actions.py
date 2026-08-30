from __future__ import annotations

from pi_coding_agent.tui.actions import APP_ACTIONS, migrate_keybindings


def test_all_frozen_product_actions_are_registered() -> None:
    assert set(APP_ACTIONS) == {
        "app.interrupt",
        "app.clear",
        "app.exit",
        "app.suspend",
        "app.thinking.cycle",
        "app.model.cycleForward",
        "app.model.cycleBackward",
        "app.model.select",
        "app.tools.expand",
        "app.thinking.toggle",
        "app.session.toggleNamedFilter",
        "app.editor.external",
        "app.message.copy",
        "app.message.followUp",
        "app.message.dequeue",
        "app.clipboard.pasteImage",
        "app.session.new",
        "app.session.tree",
        "app.session.fork",
        "app.session.resume",
        "app.tree.foldOrUp",
        "app.tree.unfoldOrDown",
        "app.tree.editLabel",
        "app.tree.toggleLabelTimestamp",
        "app.session.togglePath",
        "app.session.toggleSort",
        "app.session.rename",
        "app.session.delete",
        "app.session.deleteNoninvasive",
        "app.models.save",
        "app.models.enableAll",
        "app.models.clearAll",
        "app.models.toggleProvider",
        "app.models.reorderUp",
        "app.models.reorderDown",
        "app.tree.filter.default",
        "app.tree.filter.noTools",
        "app.tree.filter.userOnly",
        "app.tree.filter.labeledOnly",
        "app.tree.filter.all",
        "app.tree.filter.cycleForward",
        "app.tree.filter.cycleBackward",
    }


def test_legacy_action_names_migrate_without_overriding_canonical_values() -> None:
    migrated, changed = migrate_keybindings(
        {
            "interrupt": "ctrl+x",
            "app.interrupt": "escape",
            "cycleModelForward": "ctrl+p",
            "third.party.action": "f12",
        }
    )

    assert changed is True
    assert migrated["app.interrupt"] == "escape"
    assert migrated["app.model.cycleForward"] == "ctrl+p"
    assert migrated["third.party.action"] == "f12"
    assert "interrupt" not in migrated
