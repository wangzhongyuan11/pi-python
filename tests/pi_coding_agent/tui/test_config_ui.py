from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from pi_agent import Agent
from pi_ai import FakeProvider, fake_model
from pi_coding_agent.agent_session import AgentSession
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.services import create_product_services
from pi_coding_agent.session.manager import SessionManager
from pi_coding_agent.session.models import ModelChangeEntry, ThinkingLevelChangeEntry
from pi_coding_agent.tui.config_ui import (
    ModelOption,
    ModelSettingsController,
    ModelSettingsSelector,
)


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


def test_controller_applies_and_persists_model_and_thinking_selection(tmp_path: Path) -> None:
    class MultiModelProvider(FakeProvider):
        @property
        def models(self):  # type: ignore[no-untyped-def,override]
            first = fake_model()
            return (first, replace(first, id="fake-2", name="Fake Two"))

    provider = MultiModelProvider()
    runtime = ModelRuntime(provider=provider, model=provider.models[0])
    manager = SessionManager.in_memory(
        cwd=tmp_path, session_id="settings", timestamp="2026-08-26T00:00:00Z"
    )
    session = AgentSession(
        agent=Agent(model=provider.models[0], stream_function=provider.stream),
        session_manager=manager,
        services=create_product_services(tmp_path),
    )
    controller = ModelSettingsController(
        session=session,
        model_runtime=runtime,
        entry_id_factory=iter(("model-change", "thinking-change")).__next__,
        timestamp_factory=lambda: "2026-08-26T00:00:01Z",
    )

    controller.apply("fake-2", "low")

    assert session.state.model.id == "fake-2"
    assert session.state.thinking_level == "low"
    assert isinstance(manager.entries[0], ModelChangeEntry)
    assert isinstance(manager.entries[1], ThinkingLevelChangeEntry)
