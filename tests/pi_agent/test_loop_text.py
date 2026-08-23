from __future__ import annotations

import asyncio

from pi_agent.context import AgentContext
from pi_agent.events import AgentEvent
from pi_agent.loop import AgentLoopConfig, run_agent_loop
from pi_ai import (
    AssistantMessage,
    FakeProvider,
    TextContent,
    UserMessage,
    fake_assistant_message,
    fake_model,
)


def _user(text: str = "hello") -> UserMessage:
    return UserMessage(content=(TextContent(text=text),), timestamp=1)


def test_text_loop_returns_messages_and_emits_complete_lifecycle() -> None:
    async def scenario() -> None:
        provider = FakeProvider([fake_assistant_message("answer", timestamp=2)], chunk_size=3)
        events: list[AgentEvent] = []
        prompt = _user()

        new_messages = await run_agent_loop(
            (prompt,),
            AgentContext(system_prompt="system", messages=()),
            AgentLoopConfig(
                model=fake_model(),
                stream_function=provider.stream,
                event_sink=events.append,
            ),
        )

        assert new_messages == (prompt, fake_assistant_message("answer", timestamp=2))
        assert [event.type for event in events] == [
            "agent_start",
            "turn_start",
            "message_start",
            "message_end",
            "message_start",
            "message_update",
            "message_update",
            "message_update",
            "message_update",
            "message_end",
            "turn_end",
            "agent_end",
        ]
        assert provider.calls[0][1].system_prompt == "system"
        assert provider.calls[0][1].messages == (prompt,)

    asyncio.run(scenario())


def test_text_loop_accepts_empty_and_length_responses() -> None:
    async def scenario() -> None:
        empty = fake_assistant_message((), stop_reason="stop", timestamp=2)
        limited = fake_assistant_message("partial", stop_reason="length", timestamp=3)
        provider = FakeProvider([empty, limited])
        config = AgentLoopConfig(model=fake_model(), stream_function=provider.stream)

        empty_result = await run_agent_loop(
            (_user("empty"),), AgentContext(system_prompt="", messages=()), config
        )
        length_result = await run_agent_loop(
            (_user("length"),), AgentContext(system_prompt="", messages=()), config
        )

        assert empty_result[-1] == empty
        assert length_result[-1] == limited

    asyncio.run(scenario())


def test_provider_error_is_a_terminal_message_not_an_exception() -> None:
    async def scenario() -> None:
        failure = fake_assistant_message(
            (), stop_reason="error", error_message="offline failure", timestamp=2
        )
        provider = FakeProvider([failure])
        events: list[AgentEvent] = []

        result = await run_agent_loop(
            (_user(),),
            AgentContext(system_prompt="", messages=()),
            AgentLoopConfig(
                model=fake_model(),
                stream_function=provider.stream,
                event_sink=events.append,
            ),
        )

        assert result[-1] == failure
        assert isinstance(result[-1], AssistantMessage)
        assert result[-1].stop_reason == "error"
        assert events[-2].type == "turn_end"
        assert events[-1].type == "agent_end"

    asyncio.run(scenario())
