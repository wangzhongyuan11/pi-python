from __future__ import annotations

import asyncio
from pathlib import Path

from pi_agent import Agent
from pi_ai import FakeProvider, fake_assistant_message, fake_model
from pi_coding_agent.agent_session import AgentSession
from pi_coding_agent.compaction.summarizer import CompactionSummarizer
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.retry import RetryPolicy
from pi_coding_agent.sdk import CreateAgentSessionOptions, create_agent_session
from pi_coding_agent.services import create_product_services
from pi_coding_agent.session.manager import SessionManager
from pi_coding_agent.session.models import CompactionEntry, MessageEntry, SessionEntry


class FakeSummarizer(CompactionSummarizer):
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], str | None]] = []

    async def summarize(
        self, entries: tuple[SessionEntry, ...], *, previous_summary: str | None
    ) -> str:
        self.calls.append((tuple(entry.id for entry in entries), previous_summary))
        return "overflow summary"


def test_context_overflow_recovers_at_most_once(tmp_path: Path) -> None:
    async def scenario() -> tuple[int, int]:
        overflow = fake_assistant_message(
            "", stop_reason="error", error_message="maximum context length exceeded"
        )
        provider = FakeProvider([overflow, overflow])
        recoveries = 0

        async def recover() -> bool:
            nonlocal recoveries
            recoveries += 1
            return True

        session = AgentSession(
            agent=Agent(model=fake_model(), stream_function=provider.stream),
            session_manager=SessionManager.in_memory(
                cwd=tmp_path, session_id="overflow", timestamp="2026-08-24T00:00:00Z"
            ),
            services=create_product_services(tmp_path),
            overflow_recovery=recover,
        )
        await session.prompt("large prompt")
        return provider.call_count, recoveries

    assert asyncio.run(scenario()) == (2, 1)


def test_overflow_recovery_and_turn_retry_keep_separate_budgets(tmp_path: Path) -> None:
    async def scenario() -> tuple[int, int, list[float]]:
        provider = FakeProvider(
            [
                fake_assistant_message(
                    "", stop_reason="error", error_message="maximum context length exceeded"
                ),
                fake_assistant_message(
                    "", stop_reason="error", error_message="503 service unavailable"
                ),
                fake_assistant_message("ok"),
            ]
        )
        recoveries = 0
        delays: list[float] = []

        async def recover() -> bool:
            nonlocal recoveries
            recoveries += 1
            return True

        async def sleep(delay: float) -> None:
            delays.append(delay)

        session = AgentSession(
            agent=Agent(model=fake_model(), stream_function=provider.stream),
            session_manager=SessionManager.in_memory(
                cwd=tmp_path, session_id="mixed", timestamp="2026-08-24T00:00:00Z"
            ),
            services=create_product_services(tmp_path),
            retry_policy=RetryPolicy(max_retries=1),
            sleep=sleep,
            overflow_recovery=recover,
        )
        await session.prompt("large prompt")
        return provider.call_count, recoveries, delays

    assert asyncio.run(scenario()) == (3, 1, [2.0])


def test_sdk_overflow_uses_compaction_without_replaying_user_prompt(tmp_path: Path) -> None:
    async def scenario() -> tuple[int, list[tuple[tuple[str, ...], str | None]], SessionManager]:
        provider = FakeProvider(
            [
                fake_assistant_message(
                    "", stop_reason="error", error_message="maximum context length exceeded"
                ),
                fake_assistant_message("recovered"),
            ]
        )
        manager = SessionManager.in_memory(
            cwd=tmp_path, session_id="sdk-overflow", timestamp="2026-08-24T00:00:00Z"
        )
        summarizer = FakeSummarizer()
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=ModelRuntime(provider=provider, model=provider.models[0]),
                session_manager=manager,
                compaction_summarizer=summarizer,
                compaction_keep_recent_tokens=1,
                compaction_token_count=lambda _entry: 1,
                entry_id_factory=iter(("user", "overflow", "compact", "answer")).__next__,
                timestamp_factory=lambda: "2026-08-24T00:00:01Z",
            )
        )
        await created.session.prompt("large prompt")
        await created.close()
        return provider.call_count, summarizer.calls, manager

    call_count, calls, manager = asyncio.run(scenario())

    assert call_count == 2
    assert calls == [(("user",), None)]
    assert (
        len(
            [
                entry
                for entry in manager.entries
                if isinstance(entry, MessageEntry) and entry.message.get("role") == "user"
            ]
        )
        == 1
    )
    compaction = next(entry for entry in manager.entries if isinstance(entry, CompactionEntry))
    assert compaction.details == {"reason": "overflow", "incremental": False}
