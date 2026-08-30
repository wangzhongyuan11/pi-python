"""Bounded product-level retry policy, separate from provider request retries."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pi_ai import AssistantMessage

type Sleep = Callable[[float], Awaitable[None]]

_NON_RETRYABLE = re.compile(
    r"insufficient_quota|out of budget|quota exceeded|billing|usage limit", re.IGNORECASE
)
_RETRYABLE = re.compile(
    r"overloaded|rate.?limit|too many requests|429|50[0234]|524|service.?unavailable|"
    r"server.?error|internal.?error|network.?error|connection.?(?:error|refused|lost)|"
    r"fetch failed|getaddrinfo|ENOTFOUND|EAI_AGAIN|upstream.?connect|reset before headers|"
    r"socket hang up|timed? out|timeout|terminated|ended without|retry delay|please retry|"
    r"ResourceExhausted",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class RetryPolicy:
    enabled: bool = True
    max_retries: int = 3
    base_delay_seconds: float = 2.0
    provider_request_retries: int = 0

    def __post_init__(self) -> None:
        if self.max_retries < 0 or self.provider_request_retries < 0 or self.base_delay_seconds < 0:
            raise ValueError("retry counts and delays must be non-negative")

    @property
    def allows_turn_retry(self) -> bool:
        return self.enabled and self.provider_request_retries == 0

    @property
    def maximum_total_requests(self) -> int:
        if self.provider_request_retries:
            return self.provider_request_retries + 1
        return self.max_retries + 1 if self.enabled else 1

    def delay(self, attempt: int) -> float:
        if attempt < 1:
            raise ValueError("retry attempt is one-based")
        return self.base_delay_seconds * 2 ** (attempt - 1)


def is_retryable_assistant_error(message: AssistantMessage) -> bool:
    error = message.error_message
    if message.stop_reason != "error" or not error or _NON_RETRYABLE.search(error):
        return False
    return _RETRYABLE.search(error) is not None


@dataclass(frozen=True, slots=True, kw_only=True)
class RetryAttemptMetadata:
    provider_attempt: int = 0
    turn_attempt: int = 0

    @property
    def total_request_attempt(self) -> int:
        return self.provider_attempt + self.turn_attempt + 1


__all__ = [
    "RetryAttemptMetadata",
    "RetryPolicy",
    "Sleep",
    "is_retryable_assistant_error",
]
