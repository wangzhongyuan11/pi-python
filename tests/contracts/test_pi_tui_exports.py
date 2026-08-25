from __future__ import annotations

import pi_tui


def test_generic_tui_core_is_exported_from_package_root() -> None:
    assert {
        "Application",
        "Box",
        "Dialog",
        "Editor",
        "HStack",
        "KeybindingRegistry",
        "MemoryTerminal",
        "ScreenRenderer",
        "SelectList",
        "Status",
        "TUI_ACTIONS",
        "Text",
        "VStack",
        "visible_width",
    } <= set(pi_tui.__all__)
