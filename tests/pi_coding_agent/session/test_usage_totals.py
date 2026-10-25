"""Phase 18.5 C-level quick wins: session usage totals."""

from __future__ import annotations

from pi_coding_agent.session.models import MessageEntry
from pi_coding_agent.session.usage_totals import UsageTotals, accumulate_usage_totals


def _assistant(usage: dict[str, object] | None) -> MessageEntry:
    message: dict[str, object] = {
        "role": "assistant",
        "content": [],
        "api": "deepseek",
        "provider": "deepseek",
        "model": "deepseek-chat",
        "stopReason": "stop",
        "timestamp": 1767225600000,
    }
    if usage is not None:
        message["usage"] = usage
    return MessageEntry.model_validate(
        {"type": "message", "id": "m1", "parentId": None, "timestamp": "2026-01-01T00:00:00Z", "message": message}
    )


def test_empty_entries_yield_zero_totals() -> None:
    totals = accumulate_usage_totals(())

    assert totals == UsageTotals()


def test_assistant_usage_accumulates_across_entries() -> None:
    first = _assistant(
        {
            "input": 100,
            "output": 20,
            "cacheRead": 50,
            "cacheWrite": 10,
            "totalTokens": 180,
            "cost": {"input": 0.01, "output": 0.004, "cacheRead": 0.0, "cacheWrite": 0.0, "total": 0.014},
        }
    )
    second = _assistant(
        {
            "input": 30,
            "output": 5,
            "cacheRead": 0,
            "cacheWrite": 0,
            "totalTokens": 35,
            "cost": {"input": 0.003, "output": 0.001, "cacheRead": 0.0, "cacheWrite": 0.0, "total": 0.004},
        }
    )

    totals = accumulate_usage_totals((first, second))

    assert totals.requests == 2
    assert totals.input_tokens == 130
    assert totals.output_tokens == 25
    assert totals.cache_read_tokens == 50
    assert totals.cache_write_tokens == 10
    assert round(totals.cost_total, 6) == 0.018


def test_missing_or_malformed_usage_counts_as_zero() -> None:
    entry = _assistant(None)
    malformed = _assistant({"input": "not-a-number", "cost": {"total": None}})

    totals = accumulate_usage_totals((entry, malformed))

    assert totals.requests == 2
    assert totals.input_tokens == 0
    assert totals.cost_total == 0.0


def test_non_assistant_messages_are_ignored() -> None:
    user = MessageEntry.model_validate(
        {
            "type": "message",
            "id": "u1",
            "parentId": None,
            "timestamp": "2026-01-01T00:00:00Z",
            "message": {"role": "user", "content": "hi", "timestamp": 1767225600000},
        }
    )

    totals = accumulate_usage_totals((user,))

    assert totals == UsageTotals()
