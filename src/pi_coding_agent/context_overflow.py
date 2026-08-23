"""Context-overflow classification and one-shot recovery port."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable

from pi_ai import AssistantMessage

type OverflowRecovery = Callable[[], Awaitable[bool]]

_OVERFLOW = re.compile(
    r"context (?:length|window)|maximum context|too many (?:input )?tokens|"
    r"prompt is too long|input length .* exceeds",
    re.IGNORECASE,
)


def is_context_overflow(message: AssistantMessage) -> bool:
    return (
        message.stop_reason == "error"
        and message.error_message is not None
        and _OVERFLOW.search(message.error_message) is not None
    )


__all__ = ["OverflowRecovery", "is_context_overflow"]
