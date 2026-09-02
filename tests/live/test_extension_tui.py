from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.live.scenarios import (
    TUI_MAX_COST_USD,
    TUI_MAX_REQUESTS,
    run_extension_tui_scenario,
)


def _assert_extension_evidence(root: Path, *, live: bool) -> None:
    evidence = run_extension_tui_scenario(root=root, live=live)

    assert 1 <= evidence.request_count <= TUI_MAX_REQUESTS
    assert evidence.total_cost <= TUI_MAX_COST_USD
    assert evidence.session_path.is_file()
    assert evidence.tool_result_count == 1
    assert evidence.hooked is True
    assert "golden-status mode=True" in evidence.transcript
    assert "golden-reloaded" in evidence.transcript
    assert "corrected-v2" in evidence.transcript


def test_golden_extension_uses_a_real_tui_process_offline(tmp_path: Path) -> None:
    _assert_extension_evidence(tmp_path, live=False)


@pytest.mark.live_provider
@pytest.mark.network
def test_live_deepseek_uses_golden_extension_through_the_real_tui(tmp_path: Path) -> None:
    if os.environ.get("PI_PYTHON_RUN_LIVE_EXTENSION_TUI") != "1":
        pytest.skip("set PI_PYTHON_RUN_LIVE_EXTENSION_TUI=1 for the authorized live run")

    _assert_extension_evidence(tmp_path, live=True)
