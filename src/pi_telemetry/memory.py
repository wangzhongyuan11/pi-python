"""Passive in-memory telemetry recording for tests and local diagnostics."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TypeVar, cast

from .protocol import (
    NOOP_TELEMETRY_CONTEXT,
    AttributeValue,
    ErrorInfo,
    SpanAttributes,
    SpanCallback,
    SpanOptions,
    SpanStatus,
    TelemetrySpan,
)

RecordedAttributeValue = str | int | float | bool | tuple[str | int | float | bool, ...]
RecordedAttributes = Mapping[str, RecordedAttributeValue]


@dataclass(frozen=True, slots=True)
class RecordedTelemetryEvent:
    name: str
    attributes: RecordedAttributes


@dataclass(frozen=True, slots=True)
class RecordedTelemetrySpan:
    id: int
    parent_id: int | None
    name: str
    attributes: RecordedAttributes
    events: tuple[RecordedTelemetryEvent, ...]
    status: SpanStatus
    settled: bool
    end_sequence: int | None = None


@dataclass(slots=True)
class _MutableEvent:
    name: str
    attributes: dict[str, RecordedAttributeValue]


@dataclass(slots=True)
class _MutableSpan:
    id: int
    parent_id: int | None
    name: str
    attributes: dict[str, RecordedAttributeValue]
    events: list[_MutableEvent] = field(default_factory=lambda: list[_MutableEvent]())
    status: SpanStatus = field(default_factory=lambda: SpanStatus(status="ok"))
    explicit_status: bool = False
    settled: bool = False
    end_sequence: int | None = None


@dataclass(slots=True)
class _State:
    spans: list[_MutableSpan] = field(default_factory=lambda: list[_MutableSpan]())
    next_span_id: int = 1
    next_end_sequence: int = 1


def _copy_attribute_value(value: AttributeValue) -> RecordedAttributeValue:
    if isinstance(value, str | int | float | bool):
        return value
    return tuple(cast("Sequence[str | int | float | bool]", value))


def _copy_attributes(attributes: SpanAttributes | None) -> dict[str, RecordedAttributeValue]:
    if attributes is None:
        return {}
    return {
        name: _copy_attribute_value(value)
        for name, value in attributes.items()
        if value is not None
    }


def _copy_status(status: SpanStatus) -> SpanStatus:
    error = status.error
    copied_error = None if error is None else ErrorInfo(name=error.name, message=error.message)
    return SpanStatus(status=status.status, error=copied_error)


def _automatic_error_status(error: BaseException) -> SpanStatus:
    try:
        return SpanStatus(
            status="error",
            error=ErrorInfo(name=type(error).__name__, message=str(error)),
        )
    except BaseException:
        return SpanStatus(status="error")


ResultT = TypeVar("ResultT")


class _InMemorySpan:
    def __init__(self, state: _State, record: _MutableSpan) -> None:
        self._state = state
        self._record = record

    def start_span(
        self,
        options: SpanOptions,
        callback: SpanCallback[ResultT],
    ) -> Awaitable[ResultT]:
        return _start_span(self._state, self._record, options, callback)

    def add_event(self, name: str, attributes: SpanAttributes | None = None) -> None:
        if self._record.settled:
            return
        try:
            copied = _copy_attributes(attributes)
            self._record.events.append(_MutableEvent(name=name, attributes=copied))
        except BaseException:
            return

    def set_attributes(self, attributes: SpanAttributes) -> None:
        if self._record.settled:
            return
        try:
            merged = dict(self._record.attributes)
            merged.update(_copy_attributes(attributes))
            self._record.attributes = merged
        except BaseException:
            return

    def set_status(self, status: SpanStatus) -> None:
        if self._record.settled:
            return
        try:
            copied = _copy_status(status)
            self._record.status = copied
            self._record.explicit_status = True
        except BaseException:
            return


def _settle(
    state: _State,
    record: _MutableSpan,
    *,
    failed: bool,
    error: BaseException | None = None,
) -> None:
    if record.settled:
        return
    if failed and not record.explicit_status and error is not None:
        record.status = _automatic_error_status(error)
    record.settled = True
    record.end_sequence = state.next_end_sequence
    state.next_end_sequence += 1


async def _finish_result(
    state: _State,
    record: _MutableSpan,
    result: ResultT | Awaitable[ResultT],
) -> ResultT:
    try:
        if inspect.isawaitable(result):
            value = await cast("Awaitable[ResultT]", result)
        else:
            value = cast("ResultT", result)
    except BaseException as error:
        _settle(state, record, failed=True, error=error)
        raise
    _settle(state, record, failed=False)
    return value


async def _finish_error(state: _State, record: _MutableSpan, error: BaseException) -> None:
    _settle(state, record, failed=True, error=error)
    raise error


def _start_span[ResultT](
    state: _State,
    parent: _MutableSpan | None,
    options: SpanOptions,
    callback: SpanCallback[ResultT],
) -> Awaitable[ResultT]:
    if parent is not None and parent.settled:
        return NOOP_TELEMETRY_CONTEXT.start_span(options, callback)

    try:
        record = _MutableSpan(
            id=state.next_span_id,
            parent_id=None if parent is None else parent.id,
            name=options.name,
            attributes=_copy_attributes(options.attributes),
        )
        state.next_span_id += 1
        state.spans.append(record)
    except BaseException:
        return NOOP_TELEMETRY_CONTEXT.start_span(options, callback)

    span: TelemetrySpan = _InMemorySpan(state, record)
    try:
        result = callback(span)
    except BaseException as error:
        return cast("Awaitable[ResultT]", _finish_error(state, record, error))
    return _finish_result(state, record, result)


class InMemoryTelemetryContext:
    """Records detached span snapshots in span-start order."""

    def __init__(self) -> None:
        self._state = _State()

    def start_span(
        self,
        options: SpanOptions,
        callback: SpanCallback[ResultT],
    ) -> Awaitable[ResultT]:
        return _start_span(self._state, None, options, callback)

    def get_spans(self) -> tuple[RecordedTelemetrySpan, ...]:
        snapshots: list[RecordedTelemetrySpan] = []
        for span in self._state.spans:
            events = tuple(
                RecordedTelemetryEvent(
                    name=event.name,
                    attributes=MappingProxyType(dict(event.attributes)),
                )
                for event in span.events
            )
            snapshots.append(
                RecordedTelemetrySpan(
                    id=span.id,
                    parent_id=span.parent_id,
                    name=span.name,
                    attributes=MappingProxyType(dict(span.attributes)),
                    events=events,
                    status=_copy_status(span.status),
                    settled=span.settled,
                    end_sequence=span.end_sequence,
                )
            )
        return tuple(snapshots)


__all__ = [
    "InMemoryTelemetryContext",
    "RecordedAttributeValue",
    "RecordedAttributes",
    "RecordedTelemetryEvent",
    "RecordedTelemetrySpan",
]
