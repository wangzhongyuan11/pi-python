"""P15.5/1.1.0 gap closure: agent_settled carries an `aborted` field."""

from __future__ import annotations

import asyncio
from pathlib import Path

from pi_ai import (
    AssistantStream,
    Context,
    FakeProvider,
    Model,
    StreamOptions,
    fake_assistant_message,
    fake_model,
)
from pi_coding_agent.extensions.events import AgentSettledEvent, ExtensionAgentEndEvent
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.sdk import CreateAgentSessionOptions, create_agent_session


class _GatedProvider(FakeProvider):
    """First stream waits on a gate so the abort lands mid-turn."""

    def __init__(self, responses: list, gate: asyncio.Event) -> None:
        super().__init__(responses)
        self._gate = gate

    def stream(
        self, model: Model, context: Context, options: StreamOptions | None = None
    ) -> AssistantStream:
        outer = AssistantStream()

        async def produce() -> None:
            await self._gate.wait()
            inner = FakeProvider.stream(self, model, context, options)
            async for event in inner:
                outer.push(event)

        task = asyncio.create_task(produce())
        task.add_done_callback(lambda completed: completed.exception())
        return outer


def test_agent_settled_event_defaults_to_not_aborted() -> None:
    event = AgentSettledEvent()
    assert event.aborted is False


def test_settled_reports_aborted_after_mid_stream_abort(tmp_path: Path) -> None:
    gate = asyncio.Event()
    provider = _GatedProvider([fake_assistant_message("long " * 80)], gate=gate)
    settled_events: list[AgentSettledEvent] = []
    end_events: list[ExtensionAgentEndEvent] = []

    async def scenario() -> None:
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=ModelRuntime(provider=provider, model=fake_model()),
            )
        )
        try:
            created.services.extensions.register_hook(
                "agent_settled",
                lambda event: settled_events.append(event),
            )
            created.services.extensions.register_hook(
                "agent_end",
                lambda event: end_events.append(event),
            )
            prompt_task = asyncio.create_task(created.session.prompt("start a long answer"))
            for _ in range(300):
                if created.session.agent.state.is_streaming:
                    break
                await asyncio.sleep(0.01)
            assert created.session.agent.state.is_streaming, "agent never started streaming"
            created.session.abort()
            gate.set()
            await asyncio.wait_for(prompt_task, 15)
        finally:
            await created.close()

    asyncio.run(scenario())
    assert settled_events and settled_events[-1].aborted is True
    # agent_end still carries the aborted terminal message (unchanged contract).
    assert end_events
