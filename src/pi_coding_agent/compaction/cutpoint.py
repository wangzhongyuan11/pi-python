"""Choose a recent-history boundary without separating Tool Results from calls."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from ..session.models import CompactionEntry, MessageEntry, SessionEntry

type TokenCounter = Callable[[SessionEntry], int]


@dataclass(frozen=True, slots=True, kw_only=True)
class CompactionCutPoint:
    first_kept_index: int
    turn_start_index: int | None
    splits_turn: bool


def _role(entry: SessionEntry) -> str | None:
    if not isinstance(entry, MessageEntry):
        return None
    role = entry.message.get("role")
    return role if isinstance(role, str) else None


def _starts_turn(entry: SessionEntry) -> bool:
    return _role(entry) in {"user", "custom", "bashExecution", "branchSummary"}


def _valid_cut(entry: SessionEntry) -> bool:
    return _role(entry) in {"user", "assistant"}


def choose_compaction_cutpoint(
    entries: Sequence[SessionEntry],
    *,
    keep_recent_tokens: int,
    token_count: TokenCounter,
    start_index: int = 0,
    end_index: int | None = None,
) -> CompactionCutPoint:
    if keep_recent_tokens < 0:
        raise ValueError("keep_recent_tokens must be non-negative")
    end = len(entries) if end_index is None else end_index
    if not 0 <= start_index <= end <= len(entries):
        raise ValueError("invalid compaction range")
    valid = [index for index in range(start_index, end) if _valid_cut(entries[index])]
    if not valid:
        return CompactionCutPoint(
            first_kept_index=start_index, turn_start_index=None, splits_turn=False
        )
    accumulated = 0
    cut_index = valid[0]
    for index in range(end - 1, start_index - 1, -1):
        accumulated += max(0, token_count(entries[index]))
        if accumulated >= keep_recent_tokens:
            cut_index = next((candidate for candidate in valid if candidate >= index), valid[-1])
            break
    while cut_index > start_index:
        previous = entries[cut_index - 1]
        if isinstance(previous, CompactionEntry) or _role(previous) is not None:
            break
        cut_index -= 1
    if _starts_turn(entries[cut_index]):
        return CompactionCutPoint(
            first_kept_index=cut_index, turn_start_index=None, splits_turn=False
        )
    turn_start = next(
        (index for index in range(cut_index, start_index - 1, -1) if _starts_turn(entries[index])),
        None,
    )
    return CompactionCutPoint(
        first_kept_index=cut_index,
        turn_start_index=turn_start,
        splits_turn=turn_start is not None,
    )


__all__ = ["CompactionCutPoint", "TokenCounter", "choose_compaction_cutpoint"]
