from __future__ import annotations

import asyncio
from pathlib import Path

from pi_agent import Agent, MessageEndEvent
from pi_ai import FakeProvider, fake_assistant_message, fake_model
from pi_coding_agent.agent_session import AgentSession
from pi_coding_agent.agent_session_events import EntryAppendedEvent
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
