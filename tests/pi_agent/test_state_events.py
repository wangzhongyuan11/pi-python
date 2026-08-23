from __future__ import annotations

import pytest

from pi_agent.events import (
    AgentEndEvent,
    AgentEventSequence,
    AgentStartEvent,
    MessageEndEvent,
    MessageStartEvent,
    MessageUpdateEvent,
    TurnEndEvent,
    TurnStartEvent,
)
from pi_agent.state import AgentState
from pi_ai import (
    AssistantMessageStartEvent,
    TextContent,
    UserMessage,
    fake_assistant_message,
    fake_model,
)


def _user() -> UserMessage:
    return UserMessage(content=(TextContent(text="hello"),), timestamp=1)


def test_agent_state_copies_transcript_and_pending_tool_ids() -> None:
    messages = [_user()]
    pending = {"call-1"}

    state = AgentState(
        system_prompt="system",
        model=fake_model(),
        messages=messages,
        is_streaming=True,
        pending_tool_calls=pending,
    )
    messages.clear()
    pending.clear()

    assert state.messages == (_user(),)
    assert state.pending_tool_calls == frozenset({"call-1"})


def test_agent_state_rejects_runtime_fields_while_idle() -> None:
    with pytest.raises(ValueError, match="idle agent cannot have a streaming message"):
        AgentState(
            system_prompt="system",
            model=fake_model(),
            streaming_message=fake_assistant_message("partial", stop_reason="pending"),
        )

    with pytest.raises(ValueError, match="idle agent cannot have pending tool calls"):
        AgentState(
            system_prompt="system",
            model=fake_model(),
            pending_tool_calls={"call-1"},
        )


def test_event_sequence_accepts_complete_text_turn() -> None:
    user = _user()
    assistant = fake_assistant_message("done")
    partial = fake_assistant_message("", stop_reason="pending")
    stream_start = AssistantMessageStartEvent(partial=partial)
    sequence = AgentEventSequence()

    for event in (
        AgentStartEvent(),
        TurnStartEvent(),
        MessageStartEvent(message=user),
        MessageEndEvent(message=user),
        MessageStartEvent(message=partial),
        MessageUpdateEvent(message=partial, assistant_message_event=stream_start),
        MessageEndEvent(message=assistant),
        TurnEndEvent(message=assistant, tool_results=()),
        AgentEndEvent(messages=(user, assistant)),
    ):
        sequence.accept(event)

    assert sequence.is_idle


def test_event_sequence_rejects_out_of_order_events() -> None:
    sequence = AgentEventSequence()

    with pytest.raises(RuntimeError, match="turn_start requires an active agent"):
        sequence.accept(TurnStartEvent())

    sequence.accept(AgentStartEvent())
    sequence.accept(TurnStartEvent())
    with pytest.raises(RuntimeError, match="message_update requires an active assistant message"):
        sequence.accept(
            MessageUpdateEvent(
                message=fake_assistant_message("", stop_reason="pending"),
                assistant_message_event=AssistantMessageStartEvent(
                    partial=fake_assistant_message("", stop_reason="pending")
                ),
            )
        )
    with pytest.raises(RuntimeError, match="agent_end requires the turn to finish"):
        sequence.accept(AgentEndEvent(messages=()))
