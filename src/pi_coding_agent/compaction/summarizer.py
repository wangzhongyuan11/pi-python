"""Replaceable compaction summarizer port."""

from __future__ import annotations

from typing import Protocol

from ..session.models import SessionEntry


class CompactionSummarizer(Protocol):
    async def summarize(
        self,
        entries: tuple[SessionEntry, ...],
        *,
        previous_summary: str | None,
    ) -> str: ...


__all__ = ["CompactionSummarizer"]
