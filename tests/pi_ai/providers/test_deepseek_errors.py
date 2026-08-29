from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator
from typing import Any, cast

from pi_ai import Context, DoneEvent, ErrorEvent, StreamOptions, UserMessage
from pi_ai.events import AssistantMessageEvent
from pi_ai.providers.deepseek.models import DEFAULT_DEEPSEEK_MODEL
from pi_ai.providers.deepseek.provider import DeepSeekProvider, create_deepseek_client


class StaticCredentialResolver:
    async def resolve(self, provider: str) -> str | None:
        return "test-key" if provider == "deepseek" else None


class RetryableError(RuntimeError):
    def __init__(self, status_code: int, *, retry_after: float | None = None) -> None:
        super().__init__("unsafe test response")
        self.status_code = status_code
        self.retry_after = retry_after


async def successful_chunks() -> AsyncIterator[object]:
    yield {"choices": [{"delta": {"content": "ok"}, "finish_reason": "stop"}]}


async def failing_chunks_after_delta() -> AsyncIterator[object]:
    yield {"choices": [{"delta": {"content": "partial"}, "finish_reason": None}]}
    raise RetryableError(500)


async def blocked_chunks() -> AsyncIterator[object]:
    await asyncio.Event().wait()
    yield dict[str, object]()


class FakeCompletions:
    def __init__(self, outcomes: deque[object]) -> None:
        self.outcomes = outcomes
        self.call_count = 0

    async def create(self, **request: Any) -> AsyncIterator[object]:
        self.call_count += 1
        outcome = self.outcomes.popleft()
        if isinstance(outcome, BaseException):
            raise outcome
        assert request["stream"] is True
        assert hasattr(outcome, "__aiter__")
        return cast("AsyncIterator[object]", outcome)


class FakeChat:
    def __init__(self, outcomes: deque[object]) -> None:
        self.completions = FakeCompletions(outcomes)


class FakeClient:
    def __init__(self, outcomes: deque[object]) -> None:
        self.chat = FakeChat(outcomes)
        self.closed = False

    async def close(self) -> None:
        self.closed = True


async def collect(
    provider: DeepSeekProvider,
    options: StreamOptions | None = None,
) -> list[AssistantMessageEvent]:
    context = Context(messages=(UserMessage(content="hello", timestamp=1),))
    return [event async for event in provider.stream(DEFAULT_DEEPSEEK_MODEL, context, options)]


def make_provider(
    outcomes: deque[object],
    *,
    retries: int,
    delays: list[float],
) -> tuple[DeepSeekProvider, FakeClient]:
    client = FakeClient(outcomes)

    async def sleep(delay: float) -> None:
        delays.append(delay)

    provider = DeepSeekProvider(
        credential_resolver=StaticCredentialResolver(),
        client_factory=lambda api_key, base_url, timeout: client,
        max_request_retries=retries,
        sleep=sleep,
        timestamp_ms=lambda: 123,
    )
    return provider, client


def test_openai_client_disables_sdk_retries_and_uses_300_second_timeout() -> None:
    async def inspect() -> None:
        client = create_deepseek_client("test-key", "https://api.deepseek.com", 300.0)
        try:
            assert client.max_retries == 0
            assert client.timeout == 300.0
        finally:
            await client.close()

    asyncio.run(inspect())


def test_retries_429_before_any_semantic_delta() -> None:
    delays: list[float] = []
    provider, client = make_provider(
        deque([RetryableError(429, retry_after=0.25), successful_chunks()]),
        retries=1,
        delays=delays,
    )

    events = asyncio.run(collect(provider))

    assert client.chat.completions.call_count == 2
    assert delays == [0.25]
    assert [event.type for event in events].count("start") == 1
    assert isinstance(events[-1], DoneEvent)


def test_caps_server_retry_delay_at_60_seconds() -> None:
    delays: list[float] = []
    provider, _ = make_provider(
        deque([RetryableError(500, retry_after=120), successful_chunks()]),
        retries=1,
        delays=delays,
    )

    asyncio.run(collect(provider))

    assert delays == [60.0]


def test_does_not_retry_after_a_semantic_delta() -> None:
    delays: list[float] = []
    provider, client = make_provider(
        deque([failing_chunks_after_delta(), successful_chunks()]),
        retries=2,
        delays=delays,
    )

    events = asyncio.run(collect(provider))

    assert client.chat.completions.call_count == 1
    assert delays == []
    assert [event.type for event in events] == [
        "start",
        "text_start",
        "text_delta",
        "error",
    ]
    assert isinstance(events[-1], ErrorEvent)
    assert "unsafe test response" not in (events[-1].error.error_message or "")


def test_retry_exhaustion_is_a_safe_terminal_error() -> None:
    delays: list[float] = []
    provider, client = make_provider(
        deque([RetryableError(500), RetryableError(500)]),
        retries=1,
        delays=delays,
    )

    events = asyncio.run(collect(provider))

    assert client.chat.completions.call_count == 2
    assert delays == [1.0]
    assert isinstance(events[-1], ErrorEvent)
    assert events[-1].reason == "error"
    assert events[-1].error.error_message == "DeepSeek request failed with HTTP 500"


def test_pre_aborted_request_is_not_sent_or_retried() -> None:
    delays: list[float] = []
    provider, client = make_provider(deque([successful_chunks()]), retries=2, delays=delays)
    abort_event = asyncio.Event()
    abort_event.set()

    events = asyncio.run(collect(provider, StreamOptions(abort_event=abort_event)))

    assert client.chat.completions.call_count == 0
    assert delays == []
    assert isinstance(events[-1], ErrorEvent)
    assert events[-1].reason == "aborted"


def test_abort_interrupts_an_idle_open_stream() -> None:
    delays: list[float] = []
    provider, client = make_provider(deque([blocked_chunks()]), retries=2, delays=delays)

    async def run() -> list[AssistantMessageEvent]:
        abort_event = asyncio.Event()
        stream = provider.stream(
            DEFAULT_DEEPSEEK_MODEL,
            Context(messages=(UserMessage(content="hello", timestamp=1),)),
            StreamOptions(abort_event=abort_event),
        )
        iterator = stream.__aiter__()
        events = [await anext(iterator)]
        abort_event.set()
        events.extend([event async for event in iterator])
        return events

    events = asyncio.run(run())

    assert client.chat.completions.call_count == 1
    assert delays == []
    assert [event.type for event in events] == ["start", "error"]
    assert isinstance(events[-1], ErrorEvent)
    assert events[-1].reason == "aborted"


def test_missing_credential_yields_actionable_error_message() -> None:
    class NoneResolver:
        async def resolve(self, provider: str) -> str | None:
            return None

    provider = DeepSeekProvider(
        credential_resolver=NoneResolver(),
        client_factory=lambda api_key, base_url, timeout: None,
        timestamp_ms=lambda: 123,
    )

    async def scenario() -> str:
        context = Context(messages=(UserMessage(content="hello", timestamp=1),))
        events = [event async for event in provider.stream(DEFAULT_DEEPSEEK_MODEL, context)]
        error_events = [event for event in events if isinstance(event, ErrorEvent)]
        assert error_events, "expected an error event"
        return error_events[-1].error.error_message or ""

    message = asyncio.run(scenario())
    assert "DEEPSEEK_API_KEY" in message
    assert message != "DeepSeek request failed"
