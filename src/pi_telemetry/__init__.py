"""Telemetry boundary for the Pi Python distribution."""

from importlib.metadata import version as _distribution_version

from .memory import InMemoryTelemetryContext, RecordedTelemetryEvent, RecordedTelemetrySpan
from .protocol import (
    NOOP_TELEMETRY_CONTEXT,
    AttributeValue,
    ErrorInfo,
    SpanAttributes,
    SpanCallback,
    SpanOptions,
    SpanStatus,
    TelemetryContext,
    TelemetryScalar,
    TelemetrySpan,
)

__version__ = _distribution_version("pi-python")

__all__ = [
    "NOOP_TELEMETRY_CONTEXT",
    "AttributeValue",
    "ErrorInfo",
    "InMemoryTelemetryContext",
    "RecordedTelemetryEvent",
    "RecordedTelemetrySpan",
    "SpanAttributes",
    "SpanCallback",
    "SpanOptions",
    "SpanStatus",
    "TelemetryContext",
    "TelemetryScalar",
    "TelemetrySpan",
    "__version__",
]
