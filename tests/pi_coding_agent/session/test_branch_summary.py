from __future__ import annotations

import asyncio
from pathlib import Path

from pi_coding_agent.branch_summary import BranchSummaryService
from pi_coding_agent.branches import diff_branch_paths
from pi_coding_agent.file_tracking import FileOperations
from pi_coding_agent.session.manager import SessionManager
from pi_coding_agent.session.models import BranchSummaryEntry, SessionEntry, SessionInfoEntry

STAMP = "2026-08-24T00:00:00.000Z"


class FakeSummarizer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    async def summarize(self, entries: tuple[SessionEntry, ...]) -> str:
        self.calls.append(tuple(item.id for item in entries))
        return f"left behind {len(entries)} entries"


def _entry(entry_id: str, parent_id: str | None) -> SessionInfoEntry:
    return SessionInfoEntry(type="session_info", id=entry_id, parent_id=parent_id, timestamp=STAMP)


def _diverged_manager(tmp_path: Path) -> SessionManager:
    manager = SessionManager.in_memory(cwd=tmp_path, session_id="s1", timestamp=STAMP)
    manager.append(_entry("root", None))
    manager.append(_entry("a", "root"))
    manager.append(_entry("b", "a"))
    manager.branch("root")
    manager.append(_entry("c", "root"))
    return manager


def _diff():
    return diff_branch_paths(
        (_entry("root", None), _entry("a", "root"), _entry("b", "a")),
        (_entry("root", None), _entry("c", "root")),
    )


def _service(manager: SessionManager, summarizer: FakeSummarizer) -> BranchSummaryService:
    return BranchSummaryService(
        session_manager=manager,
        summarizer=summarizer,
        entry_id_factory=lambda: "sum-1",
        timestamp_factory=lambda: STAMP,
    )


def _summaries(manager: SessionManager) -> list[BranchSummaryEntry]:
    return [item for item in manager.entries if isinstance(item, BranchSummaryEntry)]


def test_record_appends_exactly_one_branch_summary_entry(tmp_path: Path) -> None:
    async def scenario() -> BranchSummaryEntry:
        manager = _diverged_manager(tmp_path)
        summarizer = FakeSummarizer()
        entry = await _service(manager, summarizer).record(_diff(), target_id="c")
        assert summarizer.calls == [("a", "b")]
        assert manager.leaf_id == "sum-1"
        assert len(_summaries(manager)) == 1
        assert entry is not None
        return entry

    entry = asyncio.run(scenario())

    assert entry.type == "branch_summary"
    assert entry.id == "sum-1"
    assert entry.parent_id == "c"
    assert entry.from_id == "b"
    assert entry.summary == "left behind 2 entries"


def test_record_persists_sorted_file_lists_in_details(tmp_path: Path) -> None:
    async def scenario() -> BranchSummaryEntry | None:
        manager = _diverged_manager(tmp_path)
        file_ops = FileOperations(
            read=frozenset({"r.py"}),
            written=frozenset({"w.py"}),
            edited=frozenset(),
        )
        return await _service(manager, FakeSummarizer()).record(
            _diff(), target_id="c", file_ops=file_ops
        )

    entry = asyncio.run(scenario())

    assert entry is not None
    assert entry.details == {"readFiles": ["r.py"], "modifiedFiles": ["w.py"]}


def test_duplicate_record_is_idempotent(tmp_path: Path) -> None:
    async def scenario() -> tuple[int, int]:
        manager = _diverged_manager(tmp_path)
        summarizer = FakeSummarizer()
        service = _service(manager, summarizer)
        first = await service.record(_diff(), target_id="c")
        second = await service.record(_diff(), target_id="c")
        assert second is first
        assert len(summarizer.calls) == 1
        return len(_summaries(manager)), len(summarizer.calls)

    summary_count, call_count = asyncio.run(scenario())

    assert (summary_count, call_count) == (1, 1)


def test_record_without_abandoned_entries_appends_nothing(tmp_path: Path) -> None:
    async def scenario() -> tuple[str | None, bool]:
        manager = _diverged_manager(tmp_path)
        summarizer = FakeSummarizer()
        empty_diff = diff_branch_paths((), (_entry("root", None),))
        entry = await _service(manager, summarizer).record(empty_diff, target_id="c")
        return manager.leaf_id, entry is None

    leaf_id, nothing_recorded = asyncio.run(scenario())

    assert leaf_id == "c"
    assert nothing_recorded is True
