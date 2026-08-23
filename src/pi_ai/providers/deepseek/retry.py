"""Explicit, bounded retry policy for DeepSeek provider requests."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from openai import APIConnectionError, APITimeoutError

MAX_SERVER_RETRY_DELAY_SECONDS = 60.0


def _attribute(value: object, name: str) -> object | None:
    return cast("object | None", getattr(value, name, None))


def provider_status_code(error: BaseException) -> int | None:
    value = _attribute(error, "status_code")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def is_retryable_provider_error(error: BaseException) -> bool:
    if isinstance(error, APIConnectionError | APITimeoutError):
        return True
    status = provider_status_code(error)
    return status in (408, 409, 429) or (status is not None and status >= 500)


def _retry_after(error: BaseException) -> float | None:
    direct = _attribute(error, "retry_after")
    if isinstance(direct, int | float) and not isinstance(direct, bool) and direct > 0:
        return float(direct)

    response = _attribute(error, "response")
    headers = _attribute(response, "headers")
    if not isinstance(headers, Mapping):
        return None
    raw = cast("Mapping[object, object]", headers).get("retry-after")
    try:
        parsed = float(raw) if isinstance(raw, str | int | float) else None
    except ValueError:
        return None
    return parsed if parsed is not None and parsed > 0 else None


def retry_delay_seconds(error: BaseException, retry_number: int) -> float:
    server_delay = _retry_after(error)
    if server_delay is not None:
        return min(server_delay, MAX_SERVER_RETRY_DELAY_SECONDS)
    return min(float(2**retry_number), MAX_SERVER_RETRY_DELAY_SECONDS)


__all__ = [
    "MAX_SERVER_RETRY_DELAY_SECONDS",
    "is_retryable_provider_error",
    "provider_status_code",
    "retry_delay_seconds",
]
