from __future__ import annotations

import asyncio
import os

import pytest

from pi_ai import Context, DoneEvent, UserMessage
from pi_ai.providers.deepseek import DEFAULT_DEEPSEEK_MODEL, create_deepseek_provider
from pi_coding_agent.deepseek_credentials import DeepSeekCredentialResolver


@pytest.mark.live_provider
@pytest.mark.network
def test_live_deepseek_text_stream_requires_explicit_opt_in() -> None:
    if os.environ.get("PI_PYTHON_RUN_LIVE_DEEPSEEK") != "1":
        pytest.skip("set PI_PYTHON_RUN_LIVE_DEEPSEEK=1 after approving this exact live run")

    resolver = DeepSeekCredentialResolver(environ=os.environ)
    provider = create_deepseek_provider(
        credential_resolver=resolver,
        max_tokens=2_048,
    )
    context = Context(
        messages=(UserMessage(content="Reply with exactly: pi-python-live-ok", timestamp=0),)
    )

    async def run() -> DoneEvent:
        events = [event async for event in provider.stream(DEFAULT_DEEPSEEK_MODEL, context)]
        terminal = events[-1]
        if not isinstance(terminal, DoneEvent):
            raise AssertionError(terminal)
        return terminal

    terminal = asyncio.run(run())
    assert terminal.reason == "stop"
