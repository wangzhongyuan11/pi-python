from __future__ import annotations

from pi_coding_agent.compaction.cutpoint import choose_compaction_cutpoint
from pi_coding_agent.session.models import MessageEntry


def _entry(identifier: str, role: str) -> MessageEntry:
    return MessageEntry(
        type="message",
        id=identifier,
        parent_id=None,
        timestamp="2026-08-24T00:00:00Z",
        message={"role": role},
    )


def test_cutpoint_never_starts_at_tool_result() -> None:
    entries = (
        _entry("u1", "user"),
        _entry("a1", "assistant"),
        _entry("t1", "toolResult"),
        _entry("u2", "user"),
        _entry("a2", "assistant"),
    )
    weights = {"u1": 2, "a1": 2, "t1": 20, "u2": 2, "a2": 2}

    cut = choose_compaction_cutpoint(
        entries, keep_recent_tokens=5, token_count=lambda entry: weights[entry.id]
    )

    assert cut.first_kept_index == 3
    assert entries[cut.first_kept_index].id == "u2"
    assert not cut.splits_turn


def test_assistant_cut_reports_the_user_turn_start() -> None:
    entries = (_entry("u", "user"), _entry("a", "assistant"), _entry("t", "toolResult"))

    cut = choose_compaction_cutpoint(
        entries,
        keep_recent_tokens=2,
        token_count=lambda entry: {"u": 10, "a": 1, "t": 1}[entry.id],
    )

    assert cut.first_kept_index == 1
    assert cut.turn_start_index == 0
    assert cut.splits_turn
