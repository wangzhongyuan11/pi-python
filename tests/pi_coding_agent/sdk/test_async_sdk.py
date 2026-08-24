from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest

from pi_ai import FakeProvider, Model, fake_assistant_message, fake_model
from pi_coding_agent.branch_summary import BranchSummarizer
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.sdk import CreateAgentSessionOptions, create_agent_session
from pi_coding_agent.session.manager import SessionManager
from pi_coding_agent.session.models import (
    BranchSummaryEntry,
    ModelChangeEntry,
    SessionEntry,
    SessionInfoEntry,
    ThinkingLevelChangeEntry,
)


def _manager(cwd: Path) -> SessionManager:
    return SessionManager.in_memory(
        cwd=cwd,
        session_id="sdk-session",
        timestamp="2026-08-24T00:00:00.000Z",
    )


def test_async_factory_composes_prompt_path_and_context_manager_cleanup(tmp_path: Path) -> None:
    async def scenario() -> tuple[bool, int, tuple[str, ...]]:
        provider = FakeProvider([fake_assistant_message("sdk answer")])
        runtime = ModelRuntime(provider=provider, model=provider.models[0])
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=runtime,
                session_manager=_manager(tmp_path),
                agent_clock=lambda: 1,
                entry_id_factory=iter(("user", "assistant")).__next__,
                timestamp_factory=lambda: "2026-08-24T00:00:01.000Z",
            )
        )
        owned_session = created.session

        async with created as active:
            assert active is created
            await active.session.prompt("hello from sdk")

        return (
            owned_session.is_closed,
            provider.call_count,
            tuple(message.role for message in owned_session.messages),
        )

    closed, call_count, roles = asyncio.run(scenario())

    assert closed
    assert call_count == 1
    assert roles == ("user", "assistant")


def test_async_context_cleanup_runs_when_caller_raises(tmp_path: Path) -> None:
    async def scenario() -> bool:
        provider = FakeProvider()
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=ModelRuntime(provider=provider, model=provider.models[0]),
                session_manager=_manager(tmp_path),
            )
        )
        owned_session = created.session
        with pytest.raises(RuntimeError, match="caller failed"):
            async with created:
                raise RuntimeError("caller failed")
        return owned_session.is_closed

    assert asyncio.run(scenario())


def test_factory_rejects_session_cwd_mismatch(tmp_path: Path) -> None:
    async def scenario() -> None:
        provider = FakeProvider()
        with pytest.raises(ValueError, match="session cwd"):
            await create_agent_session(
                CreateAgentSessionOptions(
                    cwd=tmp_path / "requested",
                    model_runtime=ModelRuntime(provider=provider, model=provider.models[0]),
                    session_manager=_manager(tmp_path / "stored"),
                )
            )

    asyncio.run(scenario())


class FakeBranchSummarizer(BranchSummarizer):
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    async def summarize(self, entries: tuple[SessionEntry, ...]) -> str:
        self.calls.append(tuple(entry.id for entry in entries))
        return "abandoned work"


def test_sdk_branch_navigation_can_persist_divergent_summary(tmp_path: Path) -> None:
    async def scenario() -> tuple[FakeBranchSummarizer, SessionManager, tuple[str, ...]]:
        manager = _manager(tmp_path)
        manager.append(
            SessionInfoEntry(
                type="session_info", id="root", parent_id=None, timestamp="2026-08-24T00:00:01Z"
            )
        )
        manager.append(
            SessionInfoEntry(
                type="session_info", id="target", parent_id="root", timestamp="2026-08-24T00:00:02Z"
            )
        )
        manager.branch("root")
        manager.append(
            SessionInfoEntry(
                type="session_info",
                id="abandoned",
                parent_id="root",
                timestamp="2026-08-24T00:00:03Z",
            )
        )
        provider = FakeProvider()
        summarizer = FakeBranchSummarizer()
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=ModelRuntime(provider=provider, model=provider.models[0]),
                session_manager=manager,
                branch_summarizer=summarizer,
                entry_id_factory=lambda: "summary",
                timestamp_factory=lambda: "2026-08-24T00:00:04Z",
            )
        )
        entry = await created.session.branch("target", summarize=True)
        roles = tuple(message.role for message in created.session.messages)
        await created.close()
        assert isinstance(entry, BranchSummaryEntry)
        return summarizer, manager, roles

    summarizer, manager, roles = asyncio.run(scenario())

    assert summarizer.calls == [("abandoned",)]
    assert manager.leaf_id == "summary"
    assert roles == ("branchSummary",)


class MultiModelFakeProvider(FakeProvider):
    def __init__(self) -> None:
        super().__init__()
        self._available_models = (
            fake_model(),
            replace(fake_model(), id="fake-2", name="Second Fake Model"),
        )

    @property
    def models(self) -> tuple[Model, ...]:
        return self._available_models


def test_sdk_resume_restores_recorded_model_and_thinking_level(tmp_path: Path) -> None:
    async def scenario() -> tuple[str, str]:
        manager = _manager(tmp_path)
        manager.append(
            SessionInfoEntry(
                type="session_info", id="root", parent_id=None, timestamp="2026-08-24T00:00:01Z"
            )
        )
        manager.append(
            ModelChangeEntry(
                type="model_change",
                id="model",
                parent_id="root",
                timestamp="2026-08-24T00:00:02Z",
                provider="fake",
                model_id="fake-2",
            )
        )
        manager.append(
            ThinkingLevelChangeEntry(
                type="thinking_level_change",
                id="thinking",
                parent_id="model",
                timestamp="2026-08-24T00:00:03Z",
                thinking_level="low",
            )
        )
        provider = MultiModelFakeProvider()
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=ModelRuntime(provider=provider, model=provider.models[0]),
                session_manager=manager,
                thinking_level="high",
            )
        )
        state = created.session.state
        await created.close()
        return state.model.id, state.thinking_level

    assert asyncio.run(scenario()) == ("fake-2", "low")
