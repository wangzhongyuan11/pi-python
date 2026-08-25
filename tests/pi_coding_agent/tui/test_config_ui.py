from __future__ import annotations

import pytest

from pi_coding_agent.tui.config_ui import ModelOption, ModelSettingsSelector


def _models() -> tuple[ModelOption, ...]:
    return (
        ModelOption(id="deepseek-v4-flash", name="Flash", max_thinking="high"),
        ModelOption(id="deepseek-v4-pro", name="Pro"),
    )


def test_current_model_is_highlighted_and_unknown_current_rejected() -> None:
    selector = ModelSettingsSelector(_models(), current_model_id="deepseek-v4-pro")
    assert selector.current_model_id == "deepseek-v4-pro"

    with pytest.raises(ValueError):
        ModelSettingsSelector(_models(), current_model_id="missing-model")


def test_model_cycling_wraps_and_persists_via_callback() -> None:
    changes: list[tuple[str, str]] = []
    selector = ModelSettingsSelector(
        _models(),
        current_model_id="deepseek-v4-pro",
        current_thinking="high",
        on_change=lambda model, level: changes.append((model, level)),
    )

    selector.cycle_model()
    assert selector.current_model_id == "deepseek-v4-flash"
    selector.confirm()

    selector.cycle_model()
    assert selector.current_model_id == "deepseek-v4-pro"
    selector.confirm()

    assert changes == [("deepseek-v4-flash", "high"), ("deepseek-v4-pro", "high")]


def test_thinking_cycles_only_within_model_capability() -> None:
    selector = ModelSettingsSelector(
        _models(),
        current_model_id="deepseek-v4-flash",
        current_thinking="high",
    )

    selector.cycle_thinking()
    assert selector.current_thinking == "off"

    for _ in range(6):
        selector.cycle_thinking()

    assert selector.current_thinking == "minimal"
    assert selector.current_thinking != "xhigh"

    with pytest.raises(ValueError):
        selector.set_thinking("max")


def test_direct_set_updates_selection() -> None:
    selector = ModelSettingsSelector(_models(), current_model_id="deepseek-v4-flash")
    selector.set_thinking("low")

    assert selector.current_thinking == "low"
