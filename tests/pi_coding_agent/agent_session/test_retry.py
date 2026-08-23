from __future__ import annotations

import asyncio
from pathlib import Path

from pi_agent import Agent
from pi_ai import FakeProvider, fake_assistant_message, fake_model
from pi_coding_agent.agent_session import AgentSession
from pi_coding_agent.agent_session_events import AutoRetryEndEvent, AutoRetryStartEvent
from pi_coding_agent.retry import RetryPolicy, Sleep
from pi_coding_agent.services import create_product_services
from pi_coding_agent.session.manager import SessionManager


def _session(tmp_path: Path, provider: FakeProvider, *, sleep: Sleep) -> AgentSession:
    return AgentSession(
        agent=Agent(model=fake_model(), stream_function=provider.stream),
        session_manager=SessionManager.in_memory(
            cwd=tmp_path, session_id="retry", timestamp="2026-08-24T00:00:00Z"
        ),
        services=create_product_services(tmp_path),
        retry_policy=RetryPolicy(),
        sleep=sleep,
    )


def test_retry_succeeds_with_exponential_delays_and_one_user_message(tmp_path: Path) -> None:
    async def scenario() -> tuple[list[float], list[object], AgentSession, FakeProvider]:
        provider = FakeProvider(
            [
                fake_assistant_message(
                    "fail", stop_reason="error", error_message="503 service unavailable"
                ),
                fake_assistant_message(
                    "fail", stop_reason="error", error_message="503 service unavailable"
                ),
                fake_assistant_message("ok"),
            ]
        )
        delays: list[float] = []

        async def sleep(delay: float) -> None:
            delays.append(delay)

        session = _session(tmp_path, provider, sleep=sleep)
        events: list[object] = []
        session.subscribe(lambda event, _signal: events.append(event))
        await session.prompt("hello")
        return delays, events, session, provider

    delays, events, session, provider = asyncio.run(scenario())
    assert delays == [2.0, 4.0]
    assert provider.call_count == 3
    assert [message.role for message in session.messages] == ["user", "assistant"]
    assert [event.attempt for event in events if isinstance(event, AutoRetryStartEvent)] == [1, 2]
    assert any(isinstance(event, AutoRetryEndEvent) and event.success for event in events)


def test_retry_exhausts_after_three_retries(tmp_path: Path) -> None:
    async def scenario() -> tuple[int, AutoRetryEndEvent]:
        failure = fake_assistant_message(
            "fail", stop_reason="error", error_message="503 service unavailable"
        )
        provider = FakeProvider([failure, failure, failure, failure])

        async def no_sleep(_delay: float) -> None:
            return None

        session = _session(tmp_path, provider, sleep=no_sleep)
        endings: list[AutoRetryEndEvent] = []
        session.subscribe(
            lambda event, _signal: endings.append(event)
            if isinstance(event, AutoRetryEndEvent)
            else None
        )
        await session.prompt("hello")
        return provider.call_count, endings[-1]

    calls, ending = asyncio.run(scenario())
    assert calls == 4
    assert (
        not ending.success
        and ending.attempt == 3
        and ending.final_error == "503 service unavailable"
    )


def test_retry_can_be_cancelled_during_backoff(tmp_path: Path) -> None:
    async def scenario() -> tuple[int, AutoRetryEndEvent]:
        provider = FakeProvider(
            [
                fake_assistant_message(
                    "fail", stop_reason="error", error_message="503 service unavailable"
                )
            ]
        )
        entered = asyncio.Event()
        release = asyncio.Event()

        async def sleep(_delay: float) -> None:
            entered.set()
            await release.wait()

        session = _session(tmp_path, provider, sleep=sleep)
        endings: list[AutoRetryEndEvent] = []
        session.subscribe(
            lambda event, _signal: endings.append(event)
            if isinstance(event, AutoRetryEndEvent)
            else None
        )
        task = asyncio.create_task(session.prompt("hello"))
        await entered.wait()
        session.cancel_retry()
        release.set()
        await task
        return provider.call_count, endings[-1]

    calls, ending = asyncio.run(scenario())
    assert calls == 1
    assert not ending.success and ending.final_error == "retry cancelled"
