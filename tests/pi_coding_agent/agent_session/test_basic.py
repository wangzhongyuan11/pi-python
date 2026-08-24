from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest

from pi_agent import Agent, MessageEndEvent
from pi_ai import FakeProvider, fake_assistant_message, fake_model
from pi_coding_agent.agent_session import AgentSession, AgentSessionClosedError
from pi_coding_agent.agent_session_events import AgentSessionEvent
from pi_coding_agent.agent_session_runtime import RuntimeReason
from pi_coding_agent.services import create_product_services
from pi_coding_agent.session.manager import SessionManager
from pi_coding_agent.session.models import MessageEntry


def _manager(cwd: Path) -> SessionManager:
    return SessionManager.in_memory(
        cwd=cwd,
        session_id="session-1",
        timestamp="2026-08-24T00:00:00.000Z",
    )


def _ids() -> Iterator[str]:
    yield from ("entry-user", "entry-assistant")


def test_agent_session_owns_agent_services_and_persists_message_end_events(
    tmp_path: Path,
) -> None:
    async def scenario() -> tuple[AgentSession, list[str]]:
        provider = FakeProvider([fake_assistant_message("answer", timestamp=2)])
        agent = Agent(
            model=fake_model(),
            stream_function=provider.stream,
            clock=lambda: 1,
        )
        manager = _manager(tmp_path)
        services = create_product_services(tmp_path)
        entry_ids = _ids()
        observed_roles: list[str] = []
        session = AgentSession(
            agent=agent,
            session_manager=manager,
            services=services,
            entry_id_factory=lambda: next(entry_ids),
            timestamp_factory=lambda: "2026-08-24T00:00:01.000Z",
        )

        def observe(event: AgentSessionEvent, _signal: asyncio.Event) -> None:
            if isinstance(event, MessageEndEvent):
                latest = manager.entries[-1]
                assert isinstance(latest, MessageEntry)
                observed_roles.append(str(latest.message["role"]))

        session.subscribe(observe)
        await session.prompt("hello")

        assert session.agent is agent
        assert session.session_manager is manager
        assert session.services is services
        persisted = [entry for entry in manager.entries if isinstance(entry, MessageEntry)]
        assert len(persisted) == len(manager.entries)
        assert [entry.id for entry in persisted] == ["entry-user", "entry-assistant"]
        assert [entry.message["role"] for entry in persisted] == ["user", "assistant"]
        return session, observed_roles

    session, observed_roles = asyncio.run(scenario())

    assert observed_roles == ["user", "assistant"]
    assert [message.role for message in session.messages] == ["user", "assistant"]


def test_close_is_idempotent_and_rejects_new_prompts(tmp_path: Path) -> None:
    async def scenario() -> tuple[list[RuntimeReason], str]:
        agent = Agent(model=fake_model(), stream_function=FakeProvider().stream)
        reasons: list[RuntimeReason] = []
        session = AgentSession(
            agent=agent,
            session_manager=_manager(tmp_path),
            services=create_product_services(tmp_path),
            on_close=reasons.append,
        )

        await session.close("switch")
        await session.close("quit")
        with pytest.raises(AgentSessionClosedError) as caught:
            await session.prompt("too late")
        return reasons, str(caught.value)

    reasons, message = asyncio.run(scenario())

    assert reasons == ["switch"]
    assert message == "AgentSession is closed"
