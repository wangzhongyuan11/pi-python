"""Threshold-triggered automatic compaction (P11.5-T05)."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

from pi_ai import (
    FakeProvider,
    Usage,
    fake_model,
    UsageCost,
    fake_assistant_message,
)
from pi_coding_agent.agent_session_events import CompactionEndEvent, CompactionStartEvent
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.sdk import CreateAgentSessionOptions, create_agent_session
from pi_coding_agent.session.manager import SessionManager


def _usage(total: int) -> Usage:
    return Usage(
        input=total,
        output=0,
        cache_read=0,
        cache_write=0,
        total_tokens=total,
        cost=UsageCost(input=0, output=0, cache_read=0, cache_write=0, total=0),
    )


def _session_manager(cwd: Path) -> SessionManager:
    return SessionManager.in_memory(
        cwd=cwd,
        session_id="auto-compact",
        timestamp="2026-08-30T00:00:00.000Z",
    )


async def _run_prompt(
    tmp_path: Path,
    responses: list,
    **options,
) -> tuple[SessionManager, list]:
    provider = FakeProvider(responses)
    runtime = ModelRuntime(provider=provider, model=fake_model())
    created = await create_agent_session(
        CreateAgentSessionOptions(
            cwd=tmp_path,
            model_runtime=runtime,
            session_manager=_session_manager(tmp_path),
            compaction_reserve_tokens=100,
            agent_clock=lambda: 1,
            **options,
        )
    )
    events: list = []
    created.session.subscribe(lambda event, signal: events.append(event))
    async with created:
        await created.session.prompt("hello there")
        manager = created.session.session_manager
    return manager, events


def test_threshold_exceeded_triggers_one_auto_compaction(tmp_path: Path) -> None:
    manager, events = asyncio.run(
        _run_prompt(
            tmp_path,
            [
                replace(fake_assistant_message("turn one"), usage=_usage(128_000)),
                fake_assistant_message("## Goal\n- summarized checkpoint"),
            ],
        )
    )
    compactions = [entry for entry in manager.entries if entry.type == "compaction"]
    assert len(compactions) == 1
    assert compactions[0].details["reason"] == "threshold"
    assert compactions[0].summary == "## Goal\n- summarized checkpoint"
    start_reasons = [event.reason for event in events if isinstance(event, CompactionStartEvent)]
    assert start_reasons == ["threshold"]
    end_reasons = [event.reason for event in events if isinstance(event, CompactionEndEvent)]
    assert end_reasons == ["threshold"]


def test_below_threshold_does_not_compact(tmp_path: Path) -> None:
    manager, _events = asyncio.run(
        _run_prompt(
            tmp_path,
            [replace(fake_assistant_message("turn one"), usage=_usage(1_000))],
        )
    )
    assert not [entry for entry in manager.entries if entry.type == "compaction"]


def test_aborted_turn_does_not_compact(tmp_path: Path) -> None:
    manager, _events = asyncio.run(
        _run_prompt(
            tmp_path,
            [
                replace(
                    fake_assistant_message("partial"),
                    usage=_usage(128_000),
                    stop_reason="aborted",
                ),
            ],
        )
    )
    assert not [entry for entry in manager.entries if entry.type == "compaction"]


def test_disabled_auto_compaction_does_not_compact(tmp_path: Path) -> None:
    manager, _events = asyncio.run(
        _run_prompt(
            tmp_path,
            [replace(fake_assistant_message("turn one"), usage=_usage(128_000))],
            auto_compaction_enabled=False,
        )
    )
    assert not [entry for entry in manager.entries if entry.type == "compaction"]
