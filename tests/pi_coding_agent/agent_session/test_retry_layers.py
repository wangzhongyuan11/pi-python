from __future__ import annotations

import asyncio
from pathlib import Path

from pi_agent import Agent
from pi_ai import FakeProvider, fake_assistant_message, fake_model
from pi_coding_agent.agent_session import AgentSession
from pi_coding_agent.retry import RetryAttemptMetadata, RetryPolicy
from pi_coding_agent.services import create_product_services
from pi_coding_agent.session.manager import SessionManager


def test_retry_metadata_counts_provider_and_turn_attempts_without_multiplication() -> None:
    provider_owned = RetryPolicy(max_retries=3, provider_request_retries=2)
    session_owned = RetryPolicy(max_retries=3, provider_request_retries=0)

    assert not provider_owned.allows_turn_retry
    assert provider_owned.maximum_total_requests == 3
    assert session_owned.allows_turn_retry
    assert session_owned.maximum_total_requests == 4
    assert RetryAttemptMetadata(provider_attempt=2, turn_attempt=0).total_request_attempt == 3


def test_agent_session_does_not_multiply_exhausted_provider_retries(tmp_path: Path) -> None:
    async def scenario() -> int:
        provider = FakeProvider(
            [
                fake_assistant_message(
                    "failed after provider retries",
                    stop_reason="error",
                    error_message="503 service unavailable",
                )
            ]
        )
        session = AgentSession(
            agent=Agent(model=fake_model(), stream_function=provider.stream),
            session_manager=SessionManager.in_memory(
                cwd=tmp_path, session_id="layers", timestamp="2026-08-24T00:00:00Z"
            ),
            services=create_product_services(tmp_path),
            retry_policy=RetryPolicy(max_retries=3, provider_request_retries=2),
        )
        await session.prompt("hello")
        return provider.call_count

    assert asyncio.run(scenario()) == 1
