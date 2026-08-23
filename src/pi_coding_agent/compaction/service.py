"""Persist manual and automatic incremental compaction summaries."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Literal

from ..session.manager import SessionManager
from ..session.models import CompactionEntry, SessionEntry
from .cutpoint import CompactionCutPoint
from .summarizer import CompactionSummarizer

type CompactionReason = Literal["manual", "threshold", "overflow"]


class CompactionService:
    def __init__(
        self,
        *,
        session_manager: SessionManager,
        summarizer: CompactionSummarizer,
        entry_id_factory: Callable[[], str],
        timestamp_factory: Callable[[], str],
    ) -> None:
        self._session_manager = session_manager
        self._summarizer = summarizer
        self._entry_id_factory = entry_id_factory
        self._timestamp_factory = timestamp_factory

    async def compact(
        self,
        entries: Sequence[SessionEntry],
        cutpoint: CompactionCutPoint,
        *,
        reason: CompactionReason,
        tokens_before: int,
        previous_summary: str | None = None,
    ) -> CompactionEntry:
        if not 0 <= cutpoint.first_kept_index < len(entries):
            raise ValueError("compaction cutpoint does not identify a kept entry")
        summary_entries = tuple(entries[: cutpoint.first_kept_index])
        summary = await self._summarizer.summarize(
            summary_entries, previous_summary=previous_summary
        )
        if not summary.strip():
            raise ValueError("compaction summarizer returned an empty summary")
        entry = CompactionEntry(
            type="compaction",
            id=self._entry_id_factory(),
            parent_id=self._session_manager.leaf_id,
            timestamp=self._timestamp_factory(),
            summary=summary,
            first_kept_entry_id=entries[cutpoint.first_kept_index].id,
            tokens_before=tokens_before,
            details={"reason": reason, "incremental": previous_summary is not None},
        )
        self._session_manager.append(entry)
        return entry


__all__ = ["CompactionReason", "CompactionService"]
