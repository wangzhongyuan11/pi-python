from __future__ import annotations

import asyncio
from pathlib import Path

from pi_ai import UserMessage
from pi_ai.wire.messages import dump_message
from pi_coding_agent.compaction.cutpoint import CompactionCutPoint
from pi_coding_agent.compaction.service import CompactionService
from pi_coding_agent.session.manager import SessionManager
from pi_coding_agent.session.models import MessageEntry, SessionEntry


class FakeSummarizer:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], str | None]] = []

    async def summarize(
        self, entries: tuple[SessionEntry, ...], *, previous_summary: str | None
    ) -> str:
        self.calls.append((tuple(entry.id for entry in entries), previous_summary))
        return f"summary-{len(self.calls)}"


def _manager(tmp_path: Path) -> SessionManager:
    manager = SessionManager.in_memory(
        cwd=tmp_path, session_id="compact", timestamp="2026-08-24T00:00:00Z"
    )
    for index in range(3):
        manager.append(
            MessageEntry(
                type="message",
                id=f"m{index}",
                parent_id=manager.leaf_id,
                timestamp=f"2026-08-24T00:00:0{index + 1}Z",
                message=dump_message(UserMessage(content=f"message {index}", timestamp=index)),
            )
        )
    return manager


def test_manual_compaction_persists_cutpoint_and_incremental_summary(tmp_path: Path) -> None:
    async def scenario() -> tuple[object, FakeSummarizer, SessionManager]:
        manager = _manager(tmp_path)
        summarizer = FakeSummarizer()
        service = CompactionService(
            session_manager=manager,
            summarizer=summarizer,
            entry_id_factory=lambda: "compact-1",
            timestamp_factory=lambda: "2026-08-24T00:00:04Z",
        )
        entry = await service.compact(
            manager.entries,
            CompactionCutPoint(first_kept_index=2, turn_start_index=None, splits_turn=False),
            reason="manual",
            tokens_before=100,
            previous_summary="old summary",
        )
        return entry, summarizer, manager

    entry, summarizer, manager = asyncio.run(scenario())
    assert entry is manager.entries[-1]
    assert entry.first_kept_entry_id == "m2"  # type: ignore[union-attr]
    assert entry.details == {"reason": "manual", "incremental": True}  # type: ignore[union-attr]
    assert summarizer.calls == [(("m0", "m1"), "old summary")]
