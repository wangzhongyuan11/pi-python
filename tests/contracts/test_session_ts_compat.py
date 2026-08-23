from __future__ import annotations

import json
import os
from pathlib import Path
from typing import cast

import pytest

from pi_coding_agent.session.codec import dump_record
from pi_coding_agent.session.reader import read_session
from scripts.session_oracle import open_with_typescript, validate_python_fixture

FIXTURE = Path(__file__).parents[1] / "fixtures" / "session_v3" / "canonical.jsonl"


def test_canonical_fixture_round_trips_all_current_entry_types() -> None:
    parsed = read_session(FIXTURE)
    original = [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines()]
    dumped = [dump_record(parsed.header), *(dump_record(entry) for entry in parsed.entries)]

    assert validate_python_fixture(FIXTURE) == ("canonical-v3", 9)
    assert dumped == original
    assert {cast("str", dump_record(entry)["type"]) for entry in parsed.entries} == {
        "message",
        "thinking_level_change",
        "model_change",
        "custom",
        "custom_message",
        "branch_summary",
        "compaction",
        "label",
        "session_info",
    }


@pytest.mark.parity
def test_frozen_typescript_session_manager_opens_canonical_fixture() -> None:
    configured = os.environ.get("PI_TS_SOURCE")
    source = Path(configured) if configured else Path("D:/pi")
    if not source.is_dir() or not (source / "node_modules" / "tsx").is_dir():
        pytest.skip("frozen TypeScript checkout with dependencies is unavailable")

    assert open_with_typescript(source, FIXTURE) == ("canonical-v3", 9)
