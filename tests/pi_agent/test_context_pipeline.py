from __future__ import annotations

import asyncio
from collections.abc import Sequence

from pi_agent.context import AgentContext, build_llm_context
from pi_agent.messages import (
    AgentMessage,
    BashExecutionMessage,
    BranchSummaryMessage,
    CompactionSummaryMessage,
    CustomMessage,
    default_convert_to_llm,
)
from pi_ai import TextContent, UserMessage


def _user(text: str, timestamp: int = 1) -> UserMessage:
    return UserMessage(content=(TextContent(text=text),), timestamp=timestamp)


def _text(message: object) -> str:
    assert isinstance(message, UserMessage)
    assert not isinstance(message.content, str)
    assert isinstance(message.content[0], TextContent)
    return message.content[0].text


def test_default_conversion_maps_product_messages_and_filters_excluded_bash() -> None:
    messages = (
        _user("original"),
        BashExecutionMessage(
            command="pwd",
            output="D:/work",
            exit_code=0,
            cancelled=False,
            truncated=False,
            timestamp=2,
        ),
        BashExecutionMessage(
            command="secret-status",
            output="hidden",
            exit_code=0,
            cancelled=False,
            truncated=False,
            timestamp=3,
            exclude_from_context=True,
        ),
        CustomMessage(
            custom_type="notice",
            content="custom context",
            display=True,
            timestamp=4,
        ),
        BranchSummaryMessage(summary="branch facts", from_id="entry-1", timestamp=5),
        CompactionSummaryMessage(summary="old facts", tokens_before=900, timestamp=6),
    )

    converted = default_convert_to_llm(messages)

    assert [message.role for message in converted] == ["user"] * 5
    assert converted[0] is messages[0]
    assert "Ran `pwd`" in _text(converted[1])
    assert _text(converted[2]) == "custom context"
    assert "branch facts" in _text(converted[3])
    assert "old facts" in _text(converted[4])


def test_context_pipeline_transforms_before_converting() -> None:
    async def scenario() -> None:
        calls: list[str] = []
        original = _user("original")
        transformed = _user("transformed", timestamp=2)

        async def transform(messages: Sequence[AgentMessage]) -> Sequence[AgentMessage]:
            calls.append("transform")
            assert tuple(messages) == (original,)
            return (transformed,)

        async def convert(messages: Sequence[AgentMessage]) -> Sequence[UserMessage]:
            calls.append("convert")
            assert tuple(messages) == (transformed,)
            return (transformed,)

        context = AgentContext(system_prompt="system", messages=(original,))
        llm_context = await build_llm_context(
            context,
            transform_context=transform,
            convert_to_llm=convert,
        )

        assert calls == ["transform", "convert"]
        assert llm_context.system_prompt == "system"
        assert llm_context.messages == (transformed,)

    asyncio.run(scenario())


def test_context_pipeline_uses_immutable_snapshots() -> None:
    async def scenario() -> None:
        original_messages = [_user("one")]
        context = AgentContext(system_prompt="system", messages=original_messages)
        original_messages.append(_user("two", timestamp=2))

        llm_context = await build_llm_context(context)

        assert [_text(message) for message in llm_context.messages] == ["one"]

    asyncio.run(scenario())
