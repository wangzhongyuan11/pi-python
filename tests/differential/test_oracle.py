"""Differential oracle acceptance (P16-T01).

The Python product and the frozen upstream TypeScript must agree on the core
session-graph and compaction-cut semantics for canonical v3 fixtures once
timestamps, ids, and absolute paths are normalized away.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.differential_oracle import DifferentialOracleError, run_probe
from scripts.ts_oracle import FROZEN_COMMIT

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "differential"
SOURCE = Path("D:/pi") if Path("D:/pi").exists() else None

KEEP_RECENT_TOKENS = (50, 1000, 10000)


def _require_source() -> Path:
    if SOURCE is None:
        pytest.skip("frozen upstream source is not available")
    return SOURCE


@pytest.mark.parametrize("fixture", ["differential-linear.jsonl", "differential-branch.jsonl"])
def test_session_tree_semantics_match_typescript(fixture: str) -> None:
    source = _require_source()
    assert run_probe("tree", FIXTURES / fixture, source) is None, (
        "Python SessionTree diverged from the frozen TypeScript SessionManager"
    )


@pytest.mark.parametrize("fixture", ["differential-linear.jsonl", "differential-branch.jsonl"])
@pytest.mark.parametrize("keep_recent_tokens", KEEP_RECENT_TOKENS)
def test_compaction_cutpoint_semantics_match_typescript(
    fixture: str, keep_recent_tokens: int
) -> None:
    source = _require_source()
    assert (
        run_probe("cutpoint", FIXTURES / fixture, source, keep_recent_tokens=keep_recent_tokens)
        is None
    ), "Python compaction cutpoint diverged from the frozen TypeScript findCutPoint"


def test_oracle_rejects_a_source_that_is_not_the_frozen_commit(tmp_path: Path) -> None:
    if SOURCE is None:
        pytest.skip("frozen upstream source is not available")
    bogus = tmp_path / "not-frozen"
    bogus.mkdir()
    with pytest.raises((DifferentialOracleError, AssertionError, RuntimeError)):
        run_probe("tree", FIXTURES / "differential-linear.jsonl", bogus)


def test_oracle_cli_exits_cleanly_on_match() -> None:
    if SOURCE is None:
        pytest.skip("frozen upstream source is not available")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.differential_oracle",
            "tree",
            str(FIXTURES / "differential-linear.jsonl"),
            "--source",
            str(SOURCE),
        ],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "match"


def test_frozen_commit_constant_matches_the_adr() -> None:
    assert FROZEN_COMMIT == "e14afc648e10fb6c527ea88fa627091ada764306"
