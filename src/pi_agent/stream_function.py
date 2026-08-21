"""Host-configurable fallback stream function."""

from __future__ import annotations

from pi_ai import StreamFunction

_default_stream_function: StreamFunction | None = None


def set_default_stream_function(stream_function: StreamFunction | None) -> None:
    global _default_stream_function
    _default_stream_function = stream_function


def get_default_stream_function() -> StreamFunction:
    if _default_stream_function is None:
        raise RuntimeError(
            "No default stream function configured. Pass stream_function explicitly or "
            "call set_default_stream_function()."
        )
    return _default_stream_function


__all__ = ["get_default_stream_function", "set_default_stream_function"]
