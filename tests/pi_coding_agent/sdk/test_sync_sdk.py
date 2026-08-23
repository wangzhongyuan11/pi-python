from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from pi_ai import FakeProvider, fake_assistant_message
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.sdk import CreateAgentSessionOptions
from pi_coding_agent.session.manager import SessionManager
from pi_coding_agent.sync_sdk import SyncSdkEventLoopError, create_agent_session_sync


def _options(cwd: Path, provider: FakeProvider) -> CreateAgentSessionOptions:
    return CreateAgentSessionOptions(
        cwd=cwd,
        model_runtime=ModelRuntime(provider=provider, model=provider.models[0]),
        session_manager=SessionManager.in_memory(
            cwd=cwd,
            session_id="sync-session",
            timestamp="2026-08-24T00:00:00.000Z",
        ),
        agent_clock=lambda: 1,
        entry_id_factory=iter(("user", "assistant")).__next__,
        timestamp_factory=lambda: "2026-08-24T00:00:01.000Z",
    )


def test_sync_wrapper_runs_prompt_and_cleanup(tmp_path: Path) -> None:
    provider = FakeProvider([fake_assistant_message("sync answer")])
    created = create_agent_session_sync(_options(tmp_path, provider))

    created.prompt("hello")
    roles = tuple(message.role for message in created.session.messages)
    created.close()
    created.close()

    assert roles == ("user", "assistant")
    assert provider.call_count == 1
    assert created.is_closed


def test_sync_wrapper_rejects_calls_inside_an_active_event_loop(tmp_path: Path) -> None:
    async def scenario() -> None:
        provider = FakeProvider()
        with pytest.raises(SyncSdkEventLoopError, match="active event loop"):
            create_agent_session_sync(_options(tmp_path, provider))

    asyncio.run(scenario())
