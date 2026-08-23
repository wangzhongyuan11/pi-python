from __future__ import annotations

from typing import TypedDict

from pi_agent import BranchSummaryMessage, CompactionSummaryMessage, CustomMessage
from pi_ai import UserMessage
from pi_coding_agent.session.context import project_session_context
from pi_coding_agent.session.models import (
    CompactionEntry,
    CustomEntry,
    CustomMessageEntry,
    MessageEntry,
    ModelChangeEntry,
    SessionInfoEntry,
    ThinkingLevelChangeEntry,
)
from pi_coding_agent.session.tree import SessionTree

STAMP = "2026-08-24T00:00:00.000Z"


class _Base(TypedDict):
    id: str
    parent_id: str | None
    timestamp: str


def _base(entry_id: str, parent_id: str | None) -> _Base:
    return {"id": entry_id, "parent_id": parent_id, "timestamp": STAMP}


def test_projection_filters_state_entries_and_converts_custom_messages() -> None:
    entries = (
        MessageEntry(
            type="message",
            **_base("e1", None),
            message={"role": "user", "content": "hello", "timestamp": 1},
        ),
        CustomEntry(type="custom", **_base("e2", "e1"), custom_type="state", data={}),
        CustomMessageEntry(
            type="custom_message",
            **_base("e3", "e2"),
            custom_type="notice",
            content="visible",
            display=True,
        ),
        ThinkingLevelChangeEntry(
            type="thinking_level_change", **_base("e4", "e3"), thinking_level="high"
        ),
        ModelChangeEntry(
            type="model_change",
            **_base("e5", "e4"),
            provider="deepseek",
            model_id="deepseek-chat",
        ),
    )

    context = project_session_context(SessionTree.build(entries), "e5")

    assert isinstance(context.messages[0], UserMessage)
    assert isinstance(context.messages[1], CustomMessage)
    assert len(context.messages) == 2
    assert context.thinking_level == "high"
    assert context.model is not None
    assert (context.model.provider, context.model.model_id) == ("deepseek", "deepseek-chat")


def test_latest_compaction_replaces_old_context_and_keeps_selected_prefix() -> None:
    entries = (
        MessageEntry(
            type="message",
            **_base("old", None),
            message={"role": "user", "content": "drop", "timestamp": 1},
        ),
        MessageEntry(
            type="message",
            **_base("keep", "old"),
            message={"role": "user", "content": "keep", "timestamp": 2},
        ),
        CompactionEntry(
            type="compaction",
            **_base("compact", "keep"),
            summary="summary",
            first_kept_entry_id="keep",
            tokens_before=100,
        ),
        SessionInfoEntry(type="session_info", **_base("meta", "compact"), name="x"),
        CustomMessageEntry(
            type="custom_message",
            **_base("after", "meta"),
            custom_type="after",
            content="new",
            display=False,
        ),
    )

    context = project_session_context(SessionTree.build(entries), "after")

    assert isinstance(context.messages[0], CompactionSummaryMessage)
    assert isinstance(context.messages[1], UserMessage)
    assert context.messages[1].content == "keep"
    assert isinstance(context.messages[2], CustomMessage)


def test_branch_summary_becomes_an_agent_message() -> None:
    from pi_coding_agent.session.models import BranchSummaryEntry

    entry = BranchSummaryEntry(
        type="branch_summary",
        **_base("branch", None),
        from_id="source",
        summary="what happened",
    )

    context = project_session_context(SessionTree.build((entry,)), "branch")

    assert isinstance(context.messages[0], BranchSummaryMessage)
