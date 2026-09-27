from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

import pytest

from pi_agent import AgentTool
from pi_ai import FakeProvider, Provider, fake_assistant_message
from pi_coding_agent.agent_session import SessionOperationCancelled
from pi_coding_agent.agent_session_runtime import (
    AgentSessionRuntime,
    RuntimeComponents,
    RuntimeReason,
    RuntimeTarget,
)
from pi_coding_agent.extensions.hooks import HookOutcome
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.ports import ResourceDescriptor
from pi_coding_agent.sdk import CreateAgentSessionOptions, create_agent_session
from pi_coding_agent.services import ServiceOverrides
from pi_coding_agent.session.manager import SessionManager
from pi_coding_agent.session.models import BranchSummaryEntry, CompactionEntry, MessageEntry


@dataclass(slots=True)
class _Session:
    closed: list[RuntimeReason]

    async def close(self, reason: RuntimeReason) -> None:
        self.closed.append(reason)


class _EventSink:
    def __init__(self, observed: list[tuple[str, str | None]], *, cancel_new: bool) -> None:
        self.observed = observed
        self.cancel_new = cancel_new

    async def emit(self, event: object) -> tuple[object, ...]:
        event_type = str(cast("Any", event).type)
        reason = getattr(event, "reason", None)
        self.observed.append((event_type, reason))
        if event_type == "session_before_switch" and reason == "new" and self.cancel_new:
            self.cancel_new = False
            return (HookOutcome(ok=True, value={"cancel": True}),)
        return ()


class _ProductEventSink:
    def __init__(self, mode: Literal["compact", "tree"]) -> None:
        self.mode = mode
        self.types: list[str] = []
        self.tree_attempts = 0

    @property
    def tools(self) -> tuple[AgentTool[Any, Any], ...]:
        return ()

    @property
    def providers(self) -> tuple[Provider, ...]:
        return ()

    async def start(self) -> tuple[ResourceDescriptor, ...]:
        return ()

    async def close(self) -> None:
        return None

    async def emit(self, event: object) -> tuple[object, ...]:
        event_type = str(cast("Any", event).type)
        self.types.append(event_type)
        if self.mode == "compact" and event_type == "session_before_compact":
            return (
                HookOutcome(
                    ok=True,
                    value={"compaction": {"summary": "extension compact summary"}},
                ),
            )
        if self.mode == "tree" and event_type == "session_before_tree":
            self.tree_attempts += 1
            if self.tree_attempts == 1:
                return (HookOutcome(ok=True, value={"cancel": True}),)
            return (
                HookOutcome(
                    ok=True,
                    value={"summary": {"summary": "extension tree summary"}},
                ),
            )
        return ()

    async def emit_chained(
        self, event: object, apply_result: Callable[[object, object], None]
    ) -> tuple[object, ...]:
        del apply_result
        return await self.emit(event)


class _UnusedSummarizer:
    async def summarize(self, *args: object, **kwargs: object) -> str:
        del args, kwargs
        raise AssertionError("extension replacement should bypass the summarizer")


def _manager(cwd: Path, suffix: str) -> SessionManager:
    return SessionManager.in_memory(
        cwd=cwd,
        session_id=f"session-{suffix}",
        timestamp=f"2026-09-01T00:00:0{suffix}.000Z",
    )


def test_runtime_orders_before_shutdown_start_and_honors_cancellation(tmp_path: Path) -> None:
    async def scenario() -> tuple[bool, bool, list[tuple[str, str | None]], list[_Session]]:
        observed: list[tuple[str, str | None]] = []
        sessions: list[_Session] = []

        async def factory(target: RuntimeTarget) -> RuntimeComponents[_Session, object]:
            session = _Session([])
            sessions.append(session)
            return RuntimeComponents(
                session=session,
                services=object(),
                events=_EventSink(observed, cancel_new=target.generation == 0),
            )

        runtime = await AgentSessionRuntime[_Session, object].create(
            factory,
            cwd=tmp_path,
            session_manager=_manager(tmp_path, "1"),
        )
        cancelled = await runtime.new_session(_manager(tmp_path, "2"))
        replaced = await runtime.new_session(_manager(tmp_path, "3"))
        await runtime.close()
        return cancelled, replaced, observed, sessions

    cancelled, replaced, observed, sessions = asyncio.run(scenario())

    assert cancelled is True
    assert replaced is False
    assert observed == [
        ("session_start", "startup"),
        ("session_before_switch", "new"),
        ("session_before_switch", "new"),
        ("session_shutdown", "new"),
        ("session_start", "new"),
        ("session_shutdown", "quit"),
    ]
    assert [session.closed for session in sessions] == [["new"], ["quit"]]


def test_extension_can_replace_compaction_and_receives_after_event(tmp_path: Path) -> None:
    sink = _ProductEventSink("compact")
    provider = FakeProvider([fake_assistant_message("one"), fake_assistant_message("two")])

    async def scenario() -> CompactionEntry:
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=ModelRuntime(provider=provider, model=provider.models[0]),
                service_overrides=ServiceOverrides(extensions=sink),
                compaction_summarizer=_UnusedSummarizer(),
                compaction_keep_recent_tokens=10,
                compaction_token_count=lambda _entry: 10,
            )
        )
        await created.session.prompt("first")
        await created.session.prompt("second")
        entry = await created.session.compact()
        await created.close()
        return entry

    entry = asyncio.run(scenario())

    assert entry.summary == "extension compact summary"
    assert entry.from_hook is True
    before = sink.types.index("session_before_compact")
    assert sink.types[before + 1] == "session_compact"


def test_tree_before_event_can_cancel_then_replace_summary(tmp_path: Path) -> None:
    sink = _ProductEventSink("tree")
    provider = FakeProvider([fake_assistant_message("one"), fake_assistant_message("two")])

    async def scenario() -> tuple[str | None, BranchSummaryEntry | None, str | None]:
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=ModelRuntime(provider=provider, model=provider.models[0]),
                service_overrides=ServiceOverrides(extensions=sink),
            )
        )
        await created.session.prompt("first")
        target = next(
            entry.id
            for entry in created.session.session_manager.entries
            if isinstance(entry, MessageEntry) and entry.message["role"] == "assistant"
        )
        await created.session.prompt("second")
        old_leaf = created.session.session_manager.leaf_id
        with pytest.raises(SessionOperationCancelled):
            await created.session.branch(target, summarize=True)
        leaf_after_cancel = created.session.session_manager.leaf_id
        summary = await created.session.branch(target, summarize=True)
        await created.close()
        return old_leaf, summary, leaf_after_cancel

    old_leaf, summary, leaf_after_cancel = asyncio.run(scenario())

    assert leaf_after_cancel == old_leaf
    assert summary is not None
    assert summary.summary == "extension tree summary"
    assert summary.from_hook is True
    assert sink.types.count("session_before_tree") == 2
    assert sink.types.count("session_tree") == 1
