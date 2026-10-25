"""Session-level usage totals (Phase 18.5, upstream usage-totals parity)."""

from __future__ import annotations

from dataclasses import dataclass

from .models import MessageEntry, SessionEntry


@dataclass(frozen=True, slots=True)
class UsageTotals:
    """Accumulated token and cost totals over a session."""

    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_total: float = 0.0


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return 0.0
    return float(value) if value >= 0 else 0.0


def accumulate_usage_totals(entries: tuple[SessionEntry, ...] | list[SessionEntry]) -> UsageTotals:
    """Sum assistant-message usage across session entries (malformed values are zero)."""

    totals = UsageTotals()
    for entry in entries:
        if not isinstance(entry, MessageEntry):
            continue
        message = entry.message
        if message.get("role") != "assistant":
            continue
        usage = message.get("usage")
        if not isinstance(usage, dict):
            totals = UsageTotals(
                requests=totals.requests + 1,
                input_tokens=totals.input_tokens,
                output_tokens=totals.output_tokens,
                cache_read_tokens=totals.cache_read_tokens,
                cache_write_tokens=totals.cache_write_tokens,
                cost_total=totals.cost_total,
            )
            continue
        cost = usage.get("cost")
        cost_total = _number(cost.get("total")) if isinstance(cost, dict) else 0.0
        totals = UsageTotals(
            requests=totals.requests + 1,
            input_tokens=totals.input_tokens + int(_number(usage.get("input"))),
            output_tokens=totals.output_tokens + int(_number(usage.get("output"))),
            cache_read_tokens=totals.cache_read_tokens
            + int(_number(usage.get("cacheRead"))),
            cache_write_tokens=totals.cache_write_tokens
            + int(_number(usage.get("cacheWrite"))),
            cost_total=totals.cost_total + cost_total,
        )
    return totals


__all__ = ["UsageTotals", "accumulate_usage_totals"]
