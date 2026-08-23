from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pi_ai
from pi_ai import Context, DoneEvent, Provider, TextContent, UserMessage
from pi_ai.providers.deepseek import (
    DEFAULT_DEEPSEEK_MODEL,
    DeepSeekProvider,
    create_deepseek_provider,
)


class StaticCredentialResolver:
    async def resolve(self, provider: str) -> str | None:
        return "test-key" if provider == "deepseek" else None


async def chunks() -> AsyncIterator[object]:
    yield {"choices": [{"delta": {"reasoning_content": "brief"}, "finish_reason": None}]}
    yield {"choices": [{"delta": {"content": "answer"}, "finish_reason": "stop"}]}
    yield {
        "choices": [],
        "usage": {"prompt_tokens": 8, "completion_tokens": 4},
    }


class MockCompletions:
    def __init__(self) -> None:
        self.request: dict[str, Any] | None = None

    async def create(self, **request: Any) -> AsyncIterator[object]:
        self.request = request
        return chunks()


class MockChat:
    def __init__(self) -> None:
        self.completions = MockCompletions()


class MockClient:
    def __init__(self) -> None:
        self.chat = MockChat()
        self.closed = False

    async def close(self) -> None:
        self.closed = True


def test_exported_provider_runs_an_end_to_end_mock_stream() -> None:
    client = MockClient()
    provider = DeepSeekProvider(
        credential_resolver=StaticCredentialResolver(),
        client_factory=lambda api_key, base_url, timeout: client,
        timestamp_ms=lambda: 123,
        max_tokens=2_048,
    )
    context = Context(messages=(UserMessage(content="hello", timestamp=1),))

    async def run() -> list[object]:
        return [event async for event in provider.stream(DEFAULT_DEEPSEEK_MODEL, context)]

    events = asyncio.run(run())

    assert isinstance(provider, Provider)
    assert isinstance(events[-1], DoneEvent)
    answer = events[-1].message.content[-1]
    assert isinstance(answer, TextContent)
    assert answer.text == "answer"
    assert client.chat.completions.request is not None
    assert client.chat.completions.request["max_tokens"] == 2_048
    assert client.chat.completions.request["reasoning_effort"] == "high"
    assert client.closed is True


def test_factory_defaults_to_pro_and_zero_request_retries() -> None:
    provider = create_deepseek_provider(credential_resolver=StaticCredentialResolver())

    assert isinstance(provider, DeepSeekProvider)
    assert provider.models[-1] is DEFAULT_DEEPSEEK_MODEL


def test_deepseek_provider_is_exported_from_pi_ai() -> None:
    assert pi_ai.DeepSeekProvider is DeepSeekProvider
    assert pi_ai.create_deepseek_provider is create_deepseek_provider
