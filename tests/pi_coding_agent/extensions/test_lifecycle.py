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
