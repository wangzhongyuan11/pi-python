from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

import pytest

from tests.fakes import FakeProvider, FakeTool


class Clock(Protocol):
    def now(self) -> datetime: ...

    def advance(self, delta: timedelta) -> None: ...


def test_fake_provider_returns_scripted_responses_in_order() -> None:
    provider = FakeProvider(["first", "second"])

    assert asyncio.run(provider.respond("request-1")) == "first"
    assert asyncio.run(provider.respond("request-2")) == "second"
    assert provider.requests == ["request-1", "request-2"]

    with pytest.raises(AssertionError, match="provider script exhausted"):
        asyncio.run(provider.respond("request-3"))


def test_fake_tool_returns_scripted_results_in_order() -> None:
    tool = FakeTool(["result-1", "result-2"])

    assert asyncio.run(tool.execute({"call": 1})) == "result-1"
    assert asyncio.run(tool.execute({"call": 2})) == "result-2"
    assert tool.calls == [{"call": 1}, {"call": 2}]

    with pytest.raises(AssertionError, match="tool script exhausted"):
        asyncio.run(tool.execute({"call": 3}))


def test_fake_fixtures_start_with_empty_scripts(
    fake_provider: FakeProvider,
    fake_tool: FakeTool,
) -> None:
    assert fake_provider.requests == []
    assert fake_tool.calls == []


def test_fake_clock_and_uuid_are_deterministic(fake_clock: Clock, fixed_uuid: UUID) -> None:
    assert fake_clock.now() == datetime(2020, 1, 1, tzinfo=UTC)
    assert fixed_uuid == UUID("00000000-0000-0000-0000-000000000001")

    fake_clock.advance(timedelta(seconds=5))

    assert fake_clock.now() == datetime(2020, 1, 1, 0, 0, 5, tzinfo=UTC)
