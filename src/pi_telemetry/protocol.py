"""Public telemetry protocols and value objects."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Never, Protocol, TypeVar, cast, runtime_checkable

TelemetryScalar = str | int | float | bool
AttributeValue = TelemetryScalar | Sequence[str] | Sequence[int] | Sequence[float] | Sequence[bool]
SpanAttributes = Mapping[str, AttributeValue | None]


@dataclass(frozen=True, slots=True)
class ErrorInfo:
    """Serializable details attached to an error span status."""

    name: str
    message: str


@dataclass(frozen=True, slots=True)
class SpanStatus:
    """Final or intermediate status assigned to a telemetry span."""

    status: Literal["ok", "error"]
    error: ErrorInfo | None = None

    def __post_init__(self) -> None:
        if self.status == "ok" and self.error is not None:
            raise ValueError("ok status cannot carry error details")


@dataclass(frozen=True, slots=True)
class SpanOptions:
    """Inputs used when starting a telemetry span."""

    name: str
    attributes: SpanAttributes | None = None


ResultT = TypeVar("ResultT")
SpanCallback = Callable[["TelemetrySpan"], ResultT | Awaitable[ResultT]]


@runtime_checkable
class TelemetryContext(Protocol):
    """Starts spans without prescribing a telemetry backend."""

    def start_span(
        self,
        options: SpanOptions,
        callback: SpanCallback[ResultT],
    ) -> Awaitable[ResultT]: ...


@runtime_checkable
class TelemetrySpan(TelemetryContext, Protocol):
    """A running span that can also parent child spans."""

    def add_event(self, name: str, attributes: SpanAttributes | None = None) -> None: ...

    def set_attributes(self, attributes: SpanAttributes) -> None: ...

    def set_status(self, status: SpanStatus) -> None: ...


async def _resolve_result(result: ResultT | Awaitable[ResultT]) -> ResultT:
    if inspect.isawaitable(result):
        return await cast("Awaitable[ResultT]", result)
    return cast("ResultT", result)


async def _raise_error(error: BaseException) -> Never:
    raise error


class _NoopTelemetrySpan:
    def start_span(
        self,
        options: SpanOptions,
        callback: SpanCallback[ResultT],
    ) -> Awaitable[ResultT]:
        del options
        try:
            result = callback(self)
        except BaseException as error:
            return _raise_error(error)
        return _resolve_result(result)

    def add_event(self, name: str, attributes: SpanAttributes | None = None) -> None:
        del name, attributes

    def set_attributes(self, attributes: SpanAttributes) -> None:
        del attributes

    def set_status(self, status: SpanStatus) -> None:
        del status


NOOP_TELEMETRY_CONTEXT: TelemetryContext = _NoopTelemetrySpan()


__all__ = [
    "NOOP_TELEMETRY_CONTEXT",
    "AttributeValue",
    "ErrorInfo",
    "SpanAttributes",
    "SpanCallback",
    "SpanOptions",
    "SpanStatus",
    "TelemetryContext",
    "TelemetryScalar",
    "TelemetrySpan",
]
