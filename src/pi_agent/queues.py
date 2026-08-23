"""Independent steering and follow-up message queues."""

from __future__ import annotations

from collections import deque
from typing import Literal

from .messages import AgentMessage

type QueueMode = Literal["all", "one-at-a-time"]


class PendingMessageQueue:
    __slots__ = ("_messages", "mode")

    def __init__(self, *, mode: QueueMode = "one-at-a-time") -> None:
        self.mode = mode
        self._messages: deque[AgentMessage] = deque()

    @property
    def has_items(self) -> bool:
        return bool(self._messages)

    def enqueue(self, message: AgentMessage) -> None:
        self._messages.append(message)

    def drain(self) -> tuple[AgentMessage, ...]:
        if not self._messages:
            return ()
        if self.mode == "one-at-a-time":
            return (self._messages.popleft(),)
        drained = tuple(self._messages)
        self._messages.clear()
        return drained

    def clear(self) -> None:
        self._messages.clear()


__all__ = ["PendingMessageQueue", "QueueMode"]
