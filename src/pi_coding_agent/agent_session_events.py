"""Product lifecycle events layered over core Agent events."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Literal

from pi_agent import AgentEvent

from .session.models import MessageEntry


@dataclass(frozen=True, slots=True, kw_only=True)
class EntryAppendedEvent:
    entry: MessageEntry
    type: Literal["entry_appended"] = field(default="entry_appended", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class AutoRetryStartEvent:
    attempt: int
    max_attempts: int
    delay_seconds: float
    error_message: str
    type: Literal["auto_retry_start"] = field(default="auto_retry_start", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class AutoRetryEndEvent:
    success: bool
    attempt: int
    final_error: str | None = None
    type: Literal["auto_retry_end"] = field(default="auto_retry_end", init=False)


type AgentSessionEvent = AgentEvent | EntryAppendedEvent | AutoRetryStartEvent | AutoRetryEndEvent
type AgentSessionEventListener = Callable[
    [AgentSessionEvent, asyncio.Event], None | Awaitable[None]
]


__all__ = [
    "AgentSessionEvent",
    "AgentSessionEventListener",
    "AutoRetryEndEvent",
    "AutoRetryStartEvent",
    "EntryAppendedEvent",
]
