"""Persist one branch summary entry per abandoned branch path."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from .branches import BranchPathDiff
from .file_tracking import FileOperations, compute_file_lists
from .session.manager import SessionManager
from .session.models import BranchSummaryEntry, SessionEntry

_EMPTY_FILE_OPS = FileOperations(frozenset(), frozenset(), frozenset())


class BranchSummarizer(Protocol):
    async def summarize(self, entries: tuple[SessionEntry, ...]) -> str: ...


@dataclass(frozen=True, slots=True)
class _RecordKey:
    lca_id: str | None
    from_entry_ids: tuple[str, ...]
    target_id: str


class BranchSummaryService:
    def __init__(
        self,
        *,
        session_manager: SessionManager,
        summarizer: BranchSummarizer,
        entry_id_factory: Callable[[], str],
        timestamp_factory: Callable[[], str],
    ) -> None:
        self._session_manager = session_manager
        self._summarizer = summarizer
        self._entry_id_factory = entry_id_factory
        self._timestamp_factory = timestamp_factory
        self._recorded: dict[_RecordKey, BranchSummaryEntry] = {}

    async def record(
        self,
        diff: BranchPathDiff,
        target_id: str,
        *,
        file_ops: FileOperations | None = None,
    ) -> BranchSummaryEntry | None:
        key = _RecordKey(
            lca_id=diff.lca_id,
            from_entry_ids=tuple(entry.id for entry in diff.from_entries),
            target_id=target_id,
        )
        existing = self._recorded.get(key)
        if existing is not None:
            return existing
        if not diff.from_entries:
            return None
        summary = await self._summarizer.summarize(tuple(diff.from_entries))
        file_lists = compute_file_lists(file_ops if file_ops is not None else _EMPTY_FILE_OPS)
        self._session_manager.branch(target_id)
        entry = BranchSummaryEntry(
            type="branch_summary",
            id=self._entry_id_factory(),
            parent_id=target_id,
            timestamp=self._timestamp_factory(),
            from_id=diff.from_entries[-1].id,
            summary=summary,
            details={
                "readFiles": list(file_lists.read_files),
                "modifiedFiles": list(file_lists.modified_files),
            },
        )
        self._session_manager.append(entry)
        self._recorded[key] = entry
        return entry


__all__ = ["BranchSummarizer", "BranchSummaryService"]
