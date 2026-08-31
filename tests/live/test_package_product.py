from __future__ import annotations

import os
from pathlib import Path

import pytest

from pi_coding_agent.config.settings import SettingsManager
from pi_coding_agent.packages.manager import DefaultPackageManager
from pi_coding_agent.resources.themes import load_themes
from tests.live.scenarios import (
    TUI_MAX_COST_USD,
    TUI_MAX_REQUESTS,
    run_packaged_tui_scenario,
)


def test_installed_package_drives_a_real_tui_process_offline(tmp_path: Path) -> None:
    evidence = run_packaged_tui_scenario(root=tmp_path, live=False)

    assert evidence.request_count == 6
    assert evidence.total_cost == 0
    assert evidence.session_path.is_file()
    assert "Golden skill applied" in evidence.transcript
    assert "Golden prompt applied" in evidence.transcript

    agent_dir = tmp_path / "agent"
    manager = DefaultPackageManager(
        settings=SettingsManager.load(agent_dir=agent_dir, cwd=tmp_path / "project")
    )
    theme_roots = (root for root in manager.resource_roots() if root.kind == "theme")
    theme_paths = tuple(root.path / "golden-theme.json" for root in theme_roots)
    themes = load_themes(theme_paths, strict=True).themes
    assert [theme.name for theme in themes] == ["golden-theme"]


@pytest.mark.live_provider
@pytest.mark.network
def test_live_deepseek_uses_installed_resources_through_the_real_tui(
    tmp_path: Path,
) -> None:
    if os.environ.get("PI_PYTHON_RUN_LIVE_PACKAGE_PRODUCT") != "1":
        pytest.skip("set PI_PYTHON_RUN_LIVE_PACKAGE_PRODUCT=1 for the authorized live run")

    evidence = run_packaged_tui_scenario(root=tmp_path, live=True)

    assert 2 <= evidence.request_count <= TUI_MAX_REQUESTS
    assert evidence.total_cost <= TUI_MAX_COST_USD
    assert evidence.session_path.is_file()
    assert "golden-package-skill-v1" in evidence.transcript
    assert "golden-package-prompt-v2" in evidence.transcript
