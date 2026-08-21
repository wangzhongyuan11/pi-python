from __future__ import annotations

import asyncio

from pi_ai.context import Context
from pi_ai.events import TextDeltaEvent
from pi_ai.messages import TextContent, ThinkingContent, ToolCall, UserMessage
from pi_ai.provider import CredentialResolver, Provider, StreamOptions
from pi_ai.testing import FakeProvider, fake_assistant_message, fake_model


def test_fake_provider_is_a_provider_and_consumes_scripts_in_call_order() -> None:
    async def scenario() -> None:
        first = fake_assistant_message("first", timestamp=1)
        second = fake_assistant_message("second", timestamp=2)
        provider = FakeProvider([first, second], chunk_size=10)
        model = fake_model()
        context = Context(messages=(UserMessage(content="hello", timestamp=0),))

        assert isinstance(provider, Provider)
        assert provider.models == (model,)
        assert await provider.stream(model, context).result() == first
        assert await provider.stream(model, context).result() == second
        exhausted = await provider.stream(model, context).result()

        assert exhausted.stop_reason == "error"
        assert exhausted.error_message == "No more fake responses queued"
        assert provider.call_count == 3
        assert provider.pending_response_count == 0
        assert provider.calls == ((model, context), (model, context), (model, context))

    asyncio.run(scenario())


def test_fake_provider_streams_text_thinking_and_tools_deterministically() -> None:
    async def scenario() -> None:
        response = fake_assistant_message(
            (
                ThinkingContent(thinking="abcd"),
                TextContent(text="answer"),
                ToolCall(id="call-1", name="read", arguments={"path": "README.md"}),
            ),
            stop_reason="toolUse",
            timestamp=3,
        )
        provider = FakeProvider([response], chunk_size=2)
        stream = provider.stream(fake_model(), Context(messages=()))

        events = [event async for event in stream]

        event_types = [event.type for event in events]
        assert event_types[:11] == [
            "start",
            "thinking_start",
            "thinking_delta",
            "thinking_delta",
            "thinking_end",
            "text_start",
            "text_delta",
            "text_delta",
            "text_delta",
            "text_end",
            "toolcall_start",
        ]
        assert event_types[11:-2] == ["toolcall_delta"] * 10
        assert event_types[-2:] == ["toolcall_end", "done"]
        assert [event.delta for event in events if isinstance(event, TextDeltaEvent)] == [
            "an",
            "sw",
            "er",
        ]
        assert await stream.result() == response

    asyncio.run(scenario())


def test_fake_provider_abort_is_an_error_event_not_an_exception() -> None:
    async def scenario() -> None:
        abort_event = asyncio.Event()
        provider = FakeProvider([fake_assistant_message("abcdefgh", timestamp=4)], chunk_size=2)
        stream = provider.stream(
            fake_model(),
            Context(messages=()),
            StreamOptions(abort_event=abort_event),
        )

        seen_types: list[str] = []
        async for event in stream:
            seen_types.append(event.type)
            if isinstance(event, TextDeltaEvent):
                abort_event.set()

        result = await stream.result()
        assert seen_types == ["start", "text_start", "text_delta", "error"]
        assert result.stop_reason == "aborted"
        assert result.error_message == "Request was aborted"

    asyncio.run(scenario())


def test_fake_provider_error_script_and_queue_mutation_are_explicit() -> None:
    async def scenario() -> None:
        provider = FakeProvider()
        provider.set_responses(
            [fake_assistant_message((), stop_reason="error", error_message="scripted", timestamp=5)]
        )
        provider.append_responses([fake_assistant_message("recovered", timestamp=6)])

        error = await provider.stream(fake_model(), Context(messages=())).result()
        recovered = await provider.stream(fake_model(), Context(messages=())).result()

        assert error.stop_reason == "error"
        assert error.error_message == "scripted"
        assert recovered.content == (TextContent(text="recovered"),)

    asyncio.run(scenario())


def test_credential_resolver_is_a_minimal_async_port() -> None:
    class Resolver:
        async def resolve(self, provider: str) -> str | None:
            return "configured" if provider == "fake" else None

    resolver = Resolver()
    assert isinstance(resolver, CredentialResolver)
    assert asyncio.run(resolver.resolve("fake")) == "configured"
