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


type AgentSessionEvent = AgentEvent | EntryAppendedEvent
type AgentSessionEventListener = Callable[
    [AgentSessionEvent, asyncio.Event], None | Awaitable[None]
]


__all__ = ["AgentSessionEvent", "AgentSessionEventListener", "EntryAppendedEvent"]
