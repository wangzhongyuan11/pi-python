from __future__ import annotations

import asyncio
import json
from io import StringIO
from pathlib import Path

from pi_agent import Agent, MessageEndEvent
from pi_ai import FakeProvider, fake_assistant_message, fake_model
from pi_coding_agent.agent_session import AgentSession
from pi_coding_agent.agent_session_events import (
    AutoRetryEndEvent,
    AutoRetryStartEvent,
    CompactionEndEvent,
    CompactionStartEvent,
    EntryAppendedEvent,
)
from pi_coding_agent.compaction.service import CompactionService
from pi_coding_agent.compaction.summarizer import CompactionSummarizer
from pi_coding_agent.presenters import JsonEventPresenter
from pi_coding_agent.services import create_product_services
from pi_coding_agent.session.manager import SessionManager


def test_core_events_are_forwarded_and_each_message_is_persisted_once(tmp_path: Path) -> None:
    async def scenario() -> tuple[list[str], int]:
        agent = Agent(
            model=fake_model(),
            stream_function=FakeProvider([fake_assistant_message("done")]).stream,
        )
        timestamp = "2026-08-24T00:00:00.000Z"
        manager = SessionManager.in_memory(cwd=tmp_path, session_id="events", timestamp=timestamp)
        ids = iter(("user", "assistant"))
        session = AgentSession(
            agent=agent,
            session_manager=manager,
            services=create_product_services(tmp_path),
            entry_id_factory=ids.__next__,
            timestamp_factory=lambda: timestamp,
        )
        observed: list[str] = []

        def listener(event: object, _signal: asyncio.Event) -> None:
            if isinstance(event, MessageEndEvent):
                observed.append(f"core:{event.message.role}")
            elif isinstance(event, EntryAppendedEvent):
                observed.append(f"entry:{event.entry.message['role']}")

        session.subscribe(listener)
        await session.prompt("hello")
        return observed, len(manager.entries)

    observed, entry_count = asyncio.run(scenario())

    assert observed == ["core:user", "entry:user", "core:assistant", "entry:assistant"]
    assert entry_count == 2


class _FixedSummarizer(CompactionSummarizer):
    async def summarize(self, entries: tuple[object, ...], *, previous_summary: str | None) -> str:
        return "event summary"


def test_compaction_emits_start_and_end_product_events(tmp_path: Path) -> None:
    async def scenario() -> tuple[list[CompactionStartEvent], list[CompactionEndEvent], int]:
        agent = Agent(
            model=fake_model(),
            stream_function=FakeProvider([fake_assistant_message("done")]).stream,
        )
        timestamp = "2026-08-24T00:00:00.000Z"
        manager = SessionManager.in_memory(cwd=tmp_path, session_id="compact", timestamp=timestamp)
        session = AgentSession(
            agent=agent,
            session_manager=manager,
            services=create_product_services(tmp_path),
            compaction_service=CompactionService(
                session_manager=manager,
                summarizer=_FixedSummarizer(),
                entry_id_factory=lambda: "compaction-1",
                timestamp_factory=lambda: timestamp,
            ),
        )
        starts: list[CompactionStartEvent] = []
        ends: list[CompactionEndEvent] = []

        def listener(event: object, _signal: asyncio.Event) -> None:
            if isinstance(event, CompactionStartEvent):
                starts.append(event)
            elif isinstance(event, CompactionEndEvent):
                ends.append(event)

        session.subscribe(listener)
        await session.prompt("hello")
        entry = await session.compact()
        return starts, ends, entry.tokens_before

    starts, ends, tokens_before = asyncio.run(scenario())

    assert len(starts) == 1 and starts[0].reason == "manual"
    assert len(ends) == 1 and ends[0].reason == "manual"
    assert ends[0].tokens_before > 0
    assert ends[0].tokens_before == tokens_before


def test_compaction_events_are_presented_with_camel_case_metadata() -> None:
    stdout = StringIO()
    presenter = JsonEventPresenter(stdout)
    signal = asyncio.Event()

    presenter(CompactionStartEvent(reason="manual"), signal)
    presenter(CompactionEndEvent(reason="overflow", tokens_before=1234), signal)

    assert [json.loads(line) for line in stdout.getvalue().splitlines()] == [
        {"type": "compaction_start", "reason": "manual"},
        {"type": "compaction_end", "reason": "overflow", "tokensBefore": 1234},
    ]


def test_json_presenter_preserves_product_retry_event_metadata() -> None:
    stdout = StringIO()
    presenter = JsonEventPresenter(stdout)
    signal = asyncio.Event()

    presenter(
        AutoRetryStartEvent(
            attempt=2,
            max_attempts=3,
            delay_seconds=4.0,
            error_message="503 service unavailable",
        ),
        signal,
    )
    presenter(
        AutoRetryEndEvent(
            success=False,
            attempt=2,
            final_error="retry cancelled",
        ),
        signal,
    )

    assert [json.loads(line) for line in stdout.getvalue().splitlines()] == [
        {
            "type": "auto_retry_start",
            "attempt": 2,
            "maxAttempts": 3,
            "delayMs": 4000,
            "errorMessage": "503 service unavailable",
        },
        {
            "type": "auto_retry_end",
            "success": False,
            "attempt": 2,
            "finalError": "retry cancelled",
        },
    ]


def test_json_presenter_includes_tool_execution_payloads() -> None:
    from pi_agent import (
        ToolExecutionEndEvent,
        ToolExecutionStartEvent,
        ToolExecutionUpdateEvent,
    )
    from pi_agent.tools import AgentToolResult
    from pi_ai import TextContent

    stdout = StringIO()
    presenter = JsonEventPresenter(stdout)
    signal = asyncio.Event()
    result = AgentToolResult(
        content=(TextContent(text="git version 2.50.1"),),
        details={"exitCode": 0},
    )

    presenter(
        ToolExecutionStartEvent(tool_call_id="call_1", tool_name="bash", args={"command": "git --version"}),
        signal,
    )
    presenter(
        ToolExecutionUpdateEvent(
            tool_call_id="call_1",
            tool_name="bash",
            args={"command": "git --version"},
            partial_result=AgentToolResult(content=(TextContent(text="…running"),), details=None),
        ),
        signal,
    )
    presenter(
        ToolExecutionEndEvent(tool_call_id="call_1", tool_name="bash", result=result, is_error=False),
        signal,
    )

    assert [json.loads(line) for line in stdout.getvalue().splitlines()] == [
        {
            "type": "tool_execution_start",
            "toolCallId": "call_1",
            "toolName": "bash",
            "args": {"command": "git --version"},
        },
        {
            "type": "tool_execution_update",
            "toolCallId": "call_1",
            "toolName": "bash",
            "args": {"command": "git --version"},
            "partialResult": {"content": [{"type": "text", "text": "…running"}], "details": None},
        },
        {
            "type": "tool_execution_end",
            "toolCallId": "call_1",
            "toolName": "bash",
            "result": {"content": [{"type": "text", "text": "git version 2.50.1"}], "details": {"exitCode": 0}},
            "isError": False,
        },
    ]
