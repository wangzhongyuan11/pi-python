"""Settings-driven compaction reserveTokens (P11.5-T20)."""

from __future__ import annotations

import asyncio
import dataclasses
from pathlib import Path

from pi_ai import FakeProvider, Usage, UsageCost, fake_assistant_message, fake_model
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.ports import InMemorySettings
from pi_coding_agent.sdk import CreateAgentSessionOptions, create_agent_session
from pi_coding_agent.services import ServiceOverrides
from pi_coding_agent.session.manager import SessionManager
from pi_coding_agent.session.models import CompactionEntry


def _usage(total: int) -> Usage:
    return Usage(
        input=total,
        output=0,
        cache_read=0,
        cache_write=0,
        total_tokens=total,
        cost=UsageCost(input=0, output=0, cache_read=0, cache_write=0, total=0),
    )


def test_settings_reserve_tokens_drive_the_threshold(tmp_path: Path) -> None:
    # fake_model context window is 128000; reserving 127500 puts the compaction
    # threshold at 500 tokens so the 1500-token turn exceeds it.
    provider = FakeProvider(
        [
            dataclasses.replace(fake_assistant_message("turn one"), usage=_usage(1_500)),
            fake_assistant_message("## Goal\n- checkpoint"),
        ]
    )

    async def scenario() -> int:
        runtime = ModelRuntime(provider=provider, model=fake_model())
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=runtime,
                session_manager=SessionManager.in_memory(
                    cwd=tmp_path,
                    session_id="reserve-setting",
                    timestamp="2026-08-30T00:00:00.000Z",
                ),
                service_overrides=ServiceOverrides(
                    settings=InMemorySettings({"compaction": {"reserveTokens": 127_500}})
                ),
                agent_clock=lambda: 1,
            )
        )
        async with created:
            await created.session.prompt("hello")
            return len(
                [
                    entry
                    for entry in created.session.session_manager.entries
                    if isinstance(entry, CompactionEntry)
                ]
            )

    assert asyncio.run(scenario()) == 1
