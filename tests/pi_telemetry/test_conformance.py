from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Iterator, Mapping
from typing import Any

import pytest

from pi_telemetry import (
    NOOP_TELEMETRY_CONTEXT,
    ErrorInfo,
    InMemoryTelemetryContext,
    SpanOptions,
    SpanStatus,
    TelemetrySpan,
)


async def _await_operation[ResultT](operation: Awaitable[ResultT]) -> ResultT:
    return await operation


def test_noop_context_preserves_results_and_exceptions() -> None:
    admitted = False

    def callback(_span: object) -> int:
        nonlocal admitted
        admitted = True
        return 42

    operation = NOOP_TELEMETRY_CONTEXT.start_span(SpanOptions(name="noop"), callback)

    assert admitted is True
    assert asyncio.run(_await_operation(operation)) == 42

    expected = RuntimeError("expected")

    def fail(_span: object) -> None:
        raise expected

    with pytest.raises(RuntimeError) as captured:
        asyncio.run(
            _await_operation(NOOP_TELEMETRY_CONTEXT.start_span(SpanOptions(name="fail"), fail))
        )
    assert captured.value is expected


def test_in_memory_context_records_lifecycle_attributes_and_events() -> None:
    context = InMemoryTelemetryContext()

    async def scenario() -> str:
        def record(span: Any) -> str:
            span.set_attributes({"count": 1, "overwrite": "middle"})
            span.set_attributes({"ignored": None, "overwrite": "end"})
            span.add_event("first", {"index": 1, "ignored": None})
            span.add_event("second", {"index": 2})
            return "done"

        operation = context.start_span(
            SpanOptions(
                name="recording",
                attributes={"start": "value", "overwrite": "start", "ignored": None},
            ),
            record,
        )
        assert context.get_spans()[0].settled is False
        return await operation

    assert asyncio.run(scenario()) == "done"
    span = context.get_spans()[0]
    assert span.name == "recording"
    assert span.attributes == {"start": "value", "overwrite": "end", "count": 1}
    assert [(event.name, event.attributes) for event in span.events] == [
        ("first", {"index": 1}),
        ("second", {"index": 2}),
    ]
    assert span.status == SpanStatus(status="ok")
    assert span.settled is True
    assert span.end_sequence == 1


def test_in_memory_context_preserves_last_explicit_status() -> None:
    context = InMemoryTelemetryContext()

    async def scenario() -> None:
        def fail_after_status(span: Any) -> None:
            span.set_status(SpanStatus(status="error", error=ErrorInfo("Expected", "first")))
            span.set_status(SpanStatus(status="ok"))
            raise ValueError("business failure")

        with pytest.raises(ValueError, match="business failure"):
            await context.start_span(SpanOptions(name="explicit"), fail_after_status)

        async def reject(_span: Any) -> None:
            raise LookupError("automatic")

        with pytest.raises(LookupError, match="automatic"):
            await context.start_span(SpanOptions(name="automatic"), reject)

    asyncio.run(scenario())
    explicit, automatic = context.get_spans()
    assert explicit.status == SpanStatus(status="ok")
    assert automatic.status == SpanStatus(
        status="error",
        error=ErrorInfo(name="LookupError", message="automatic"),
    )


def test_ok_status_rejects_error_details() -> None:
    with pytest.raises(ValueError, match="ok status"):
        SpanStatus(status="ok", error=ErrorInfo(name="Invalid", message="details"))


def test_in_memory_context_records_nested_parentage_and_settlement_order() -> None:
    context = InMemoryTelemetryContext()

    async def scenario() -> None:
        async def parent_callback(parent: Any) -> None:
            first_gate = asyncio.Event()

            async def first_callback(_span: Any) -> None:
                await first_gate.wait()

            first = parent.start_span(SpanOptions(name="first-child"), first_callback)

            def finish_second(_span: TelemetrySpan) -> str:
                return "done"

            second = parent.start_span(SpanOptions(name="second-child"), finish_second)
            assert await second == "done"
            first_gate.set()
            await first

        await context.start_span(SpanOptions(name="parent"), parent_callback)

    asyncio.run(scenario())
    parent, first, second = context.get_spans()
    assert parent.parent_id is None
    assert first.parent_id == parent.id
    assert second.parent_id == parent.id
    assert second.end_sequence is not None
    assert first.end_sequence is not None
    assert parent.end_sequence is not None
    assert second.end_sequence < first.end_sequence < parent.end_sequence


def test_calls_after_settlement_are_inert_and_snapshots_are_detached() -> None:
    context = InMemoryTelemetryContext()
    captured: Any = None

    async def scenario() -> None:
        nonlocal captured

        def callback(span: Any) -> None:
            nonlocal captured
            captured = span

        await context.start_span(
            SpanOptions(name="settled", attributes={"items": ["initial"]}), callback
        )
        captured.set_attributes({"value": "late"})
        captured.add_event("late")
        captured.set_status(SpanStatus(status="error"))

        def finish_late_child(_span: TelemetrySpan) -> int:
            return 7

        assert await captured.start_span(SpanOptions(name="late-child"), finish_late_child) == 7

    asyncio.run(scenario())
    first_snapshot = context.get_spans()
    assert len(first_snapshot) == 1
    assert first_snapshot[0].attributes == {"items": ("initial",)}
    assert first_snapshot[0].events == ()
    assert first_snapshot[0].status == SpanStatus(status="ok")

    copied = dict(first_snapshot[0].attributes)
    copied["value"] = "changed"
    assert context.get_spans()[0].attributes == {"items": ("initial",)}


def test_unreadable_attribute_payload_is_passive_and_atomic() -> None:
    context = InMemoryTelemetryContext()

    class Unreadable(Mapping[str, object]):
        def __getitem__(self, key: str) -> object:
            raise RuntimeError(key)

        def __iter__(self) -> Iterator[str]:
            raise RuntimeError("enumerate")

        def __len__(self) -> int:
            raise RuntimeError("length")

    async def scenario() -> None:
        def callback(span: Any) -> None:
            span.set_attributes(Unreadable())
            span.add_event("unreadable", Unreadable())

        await context.start_span(
            SpanOptions(name="passive", attributes={"retained": "value"}), callback
        )

    asyncio.run(scenario())
    span = context.get_spans()[0]
    assert span.attributes == {"retained": "value"}
    assert span.events == ()
