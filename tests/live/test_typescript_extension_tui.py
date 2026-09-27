"""P15.5-T07 live track: a real TUI process drives a real TypeScript extension.

Offline mode scripts the provider; the live mode runs the real DeepSeek API
with hard request/cost/process ceilings (standing capped authorization).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.live.scenarios import (
    TUI_MAX_COST_USD,
    TUI_MAX_REQUESTS,
    run_typescript_extension_tui_scenario,
)


def _assert_typescript_evidence(root: Path, *, live: bool) -> None:
    evidence = run_typescript_extension_tui_scenario(root=root, live=live)

    assert 1 <= evidence.request_count <= TUI_MAX_REQUESTS
    assert evidence.total_cost <= TUI_MAX_COST_USD
    assert evidence.session_path.is_file()
    assert evidence.tool_result_count == 1


def test_official_typescript_extension_through_a_real_tui_process_offline(
    tmp_path: Path,
) -> None:
    _assert_typescript_evidence(tmp_path, live=False)


@pytest.mark.live_provider
@pytest.mark.network
def test_live_deepseek_drives_the_typescript_extension_through_the_real_tui(
    tmp_path: Path,
) -> None:
    if os.environ.get("PI_PYTHON_RUN_LIVE_TYPESCRIPT_TUI") != "1":
        pytest.skip("set PI_PYTHON_RUN_LIVE_TYPESCRIPT_TUI=1 for the authorized live run")

    _assert_typescript_evidence(tmp_path, live=True)
