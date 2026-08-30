from __future__ import annotations

import pytest

from pi_coding_agent.extensions.lifecycle import (
    ExtensionLifecycle,
    LifecycleClosedError,
)


def test_teardown_runs_once_in_reverse_order_and_is_idempotent() -> None:
    lifecycle = ExtensionLifecycle()
    calls: list[str] = []
    lifecycle.register_teardown(lambda: calls.append("first"))
    lifecycle.register_teardown(lambda: calls.append("second"))

    lifecycle.teardown()
    lifecycle.teardown()

    assert calls == ["second", "first"]
    assert not lifecycle.active


def test_stale_tokens_are_inert_after_teardown() -> None:
    lifecycle = ExtensionLifecycle()
    token = lifecycle.register_teardown(lambda: None)
    lifecycle.teardown()

    lifecycle.unregister(token)

    assert lifecycle.unregistered_count == 0


def test_registration_after_close_is_rejected_until_new_generation() -> None:
    lifecycle = ExtensionLifecycle()
    lifecycle.register_teardown(lambda: None)
    lifecycle.teardown()

    with pytest.raises(LifecycleClosedError):
        lifecycle.register_teardown(lambda: None)

    lifecycle.begin_generation()

    late_calls: list[str] = []
    lifecycle.register_teardown(lambda: late_calls.append("reloaded"))
    lifecycle.teardown()

    assert late_calls == ["reloaded"]


def test_old_token_cannot_unregister_handler_from_new_generation() -> None:
    lifecycle = ExtensionLifecycle()
    old = lifecycle.register_teardown(lambda: None)
    lifecycle.teardown()
    lifecycle.begin_generation()
    calls: list[str] = []
    lifecycle.register_teardown(lambda: calls.append("new"))

    lifecycle.unregister(old)
    lifecycle.teardown()

    assert calls == ["new"]


def test_unregister_tokens_remain_stable_after_earlier_removal() -> None:
    lifecycle = ExtensionLifecycle()
    first = lifecycle.register_teardown(lambda: None)
    calls: list[str] = []
    second = lifecycle.register_teardown(lambda: calls.append("second"))

    lifecycle.unregister(first)
    lifecycle.unregister(second)
    lifecycle.teardown()

    assert calls == []
    assert lifecycle.unregistered_count == 2


def test_teardown_isolates_handler_failures_and_continues() -> None:
    lifecycle = ExtensionLifecycle()
    calls: list[str] = []
    lifecycle.register_teardown(lambda: calls.append("first"))

    def fail() -> None:
        calls.append("failing")
        raise RuntimeError("extension cleanup failed")

    lifecycle.register_teardown(fail)
    lifecycle.register_teardown(lambda: calls.append("last"))

    errors = lifecycle.teardown()

    assert calls == ["last", "failing", "first"]
    assert len(errors) == 1
    assert isinstance(errors[0], RuntimeError)


def test_async_teardown_handlers_are_awaited() -> None:
    import asyncio

    lifecycle = ExtensionLifecycle()
    calls: list[str] = []

    async def close() -> None:
        await asyncio.sleep(0)
        calls.append("closed")

    lifecycle.register_teardown(close)

    assert asyncio.run(lifecycle.teardown_async()) == ()
    assert calls == ["closed"]
