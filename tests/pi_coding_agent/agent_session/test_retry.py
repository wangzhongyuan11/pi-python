from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic import BaseModel

from pi_agent import Agent, AgentTool, AgentToolResult, AgentToolUpdateCallback
from pi_ai import FakeProvider, TextContent, ToolCall, fake_assistant_message, fake_model
from pi_coding_agent.agent_session import AgentSession
from pi_coding_agent.agent_session_events import AutoRetryEndEvent, AutoRetryStartEvent
from pi_coding_agent.retry import RetryPolicy, Sleep
from pi_coding_agent.services import create_product_services
from pi_coding_agent.session.manager import SessionManager
from pi_coding_agent.session.models import MessageEntry


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
    assert [
        entry.message["role"]
        for entry in session.session_manager.entries
        if isinstance(entry, MessageEntry)
    ] == [
        "user",
        "assistant",
        "assistant",
        "assistant",
    ]
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
        await asyncio.wait_for(task, timeout=0.5)
        assert not release.is_set()
        return provider.call_count, endings[-1]

    calls, ending = asyncio.run(scenario())
    assert calls == 1
    assert not ending.success and ending.final_error == "retry cancelled"


class _SideEffectArgs(BaseModel):
    value: str


def test_retry_after_tool_result_does_not_reexecute_completed_tool(tmp_path: Path) -> None:
    async def scenario() -> tuple[list[str], int, list[str]]:
        executed: list[str] = []

        async def execute(
            _tool_call_id: str,
            params: _SideEffectArgs,
            _abort_event: asyncio.Event | None,
            _on_update: AgentToolUpdateCallback[dict[str, str]] | None,
        ) -> AgentToolResult[dict[str, str]]:
            executed.append(params.value)
            return AgentToolResult(
                content=(TextContent(text=params.value),),
                details={"value": params.value},
            )

        tool = AgentTool(
            name="side_effect",
            label="Side effect",
            description="Record one test side effect",
            parameter_type=_SideEffectArgs,
            execute=execute,
        )
        provider = FakeProvider(
            [
                fake_assistant_message(
                    ToolCall(
                        id="call-1",
                        name="side_effect",
                        arguments={"value": "once"},
                    ),
                    stop_reason="toolUse",
                ),
                fake_assistant_message(
                    "fail", stop_reason="error", error_message="503 service unavailable"
                ),
                fake_assistant_message("ok"),
            ]
        )

        async def no_sleep(_delay: float) -> None:
            return None

        session = AgentSession(
            agent=Agent(model=fake_model(), stream_function=provider.stream, tools=(tool,)),
            session_manager=SessionManager.in_memory(
                cwd=tmp_path, session_id="tool-retry", timestamp="2026-08-24T00:00:00Z"
            ),
            services=create_product_services(tmp_path),
            sleep=no_sleep,
        )
        await session.prompt("hello")
        persisted_roles = [
            str(entry.message["role"])
            for entry in session.session_manager.entries
            if isinstance(entry, MessageEntry)
        ]
        return executed, provider.call_count, persisted_roles

    executed, calls, persisted_roles = asyncio.run(scenario())

    assert executed == ["once"]
    assert calls == 3
    assert persisted_roles == ["user", "assistant", "toolResult", "assistant", "assistant"]
