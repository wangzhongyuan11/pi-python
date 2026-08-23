from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from pi_ai import FakeProvider, fake_assistant_message
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.sdk import CreateAgentSessionOptions, create_agent_session
from pi_coding_agent.session.manager import SessionManager


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
