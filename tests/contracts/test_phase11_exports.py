from __future__ import annotations

import pi_coding_agent.tui as tui


def test_phase11_product_tui_exports_are_public() -> None:
    assert {
        "AssistantMessageView",
        "CommandDispatcher",
        "DialogBridge",
        "InteractiveApp",
        "InteractiveOptions",
        "ModelSettingsController",
        "ModelSettingsSelector",
        "SessionSelector",
        "ToolExecutionView",
        "run_interactive",
    } <= set(tui.__all__)
