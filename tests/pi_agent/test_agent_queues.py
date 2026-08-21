from __future__ import annotations

import asyncio
from collections.abc import Sequence

import pytest

from pi_agent.agent import Agent
from pi_agent.messages import AgentMessage
from pi_agent.queues import PendingMessageQueue
from pi_ai import FakeProvider, TextContent, UserMessage, fake_assistant_message, fake_model


def _user(text: str, timestamp: int) -> UserMessage:
    return UserMessage(content=(TextContent(text=text),), timestamp=timestamp)


def _text(message: AgentMessage) -> str | None:
    if not isinstance(message, UserMessage) or isinstance(message.content, str):
        return None
    first = message.content[0]
    return first.text if isinstance(first, TextContent) else None


def test_pending_queue_drains_one_or_all_without_crossing_queues() -> None:
    one = PendingMessageQueue(mode="one-at-a-time")
    all_at_once = PendingMessageQueue(mode="all")
    messages = (_user("one", 1), _user("two", 2))
    for message in messages:
        one.enqueue(message)
        all_at_once.enqueue(message)

    assert one.drain() == (messages[0],)
    assert one.drain() == (messages[1],)
    assert all_at_once.drain() == messages
    assert not one.has_items
    assert not all_at_once.has_items


def test_steering_runs_before_follow_up_at_distinct_drain_points() -> None:
    async def scenario() -> None:
        entered = asyncio.Event()
        release = asyncio.Event()
        transform_calls = 0

        async def transform(messages: Sequence[AgentMessage]) -> Sequence[AgentMessage]:
            nonlocal transform_calls
            transform_calls += 1
            if transform_calls == 1:
                entered.set()
                await release.wait()
            return messages

        provider = FakeProvider(
            [
                fake_assistant_message("first"),
                fake_assistant_message("second"),
                fake_assistant_message("third"),
            ]
        )
        agent = Agent(
            model=fake_model(),
            stream_function=provider.stream,
            transform_context=transform,
            clock=lambda: 10,
        )

        active = asyncio.create_task(agent.prompt("start"))
        await entered.wait()
        agent.steer(_user("steer", 2))
        agent.follow_up(_user("follow", 3))
        release.set()
        await active

        assert provider.call_count == 3
        assert [_text(message) for message in provider.calls[0][1].messages if _text(message)] == [
            "start"
        ]
        assert [_text(message) for message in provider.calls[1][1].messages if _text(message)] == [
            "start",
            "steer",
        ]
        assert [_text(message) for message in provider.calls[2][1].messages if _text(message)] == [
            "start",
            "steer",
            "follow",
        ]
        assert [_text(message) for message in agent.state.messages if _text(message)] == [
            "start",
            "steer",
            "follow",
        ]

    asyncio.run(scenario())


def test_concurrent_prompt_is_rejected_with_queue_guidance() -> None:
    async def scenario() -> None:
        entered = asyncio.Event()
        release = asyncio.Event()

        async def transform(messages: Sequence[AgentMessage]) -> Sequence[AgentMessage]:
            entered.set()
            await release.wait()
            return messages

        agent = Agent(
            model=fake_model(),
            stream_function=FakeProvider([fake_assistant_message("done")]).stream,
            transform_context=transform,
        )
        active = asyncio.create_task(agent.prompt("first"))
        await entered.wait()

        with pytest.raises(RuntimeError, match=r"Use steer\(\) or follow_up\(\)"):
            await agent.prompt("second")

        release.set()
        await active

    asyncio.run(scenario())
