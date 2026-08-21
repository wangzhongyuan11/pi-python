"""Immutable request context snapshots passed to providers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .messages import Message


@dataclass(frozen=True, slots=True, init=False)
class Context:
    system_prompt: str | None
    messages: tuple[Message, ...]
    tools: tuple[object, ...] | None

    def __init__(
        self,
        *,
        messages: Iterable[Message],
        system_prompt: str | None = None,
        tools: Iterable[object] | None = None,
    ) -> None:
        object.__setattr__(self, "system_prompt", system_prompt)
        object.__setattr__(self, "messages", tuple(messages))
        object.__setattr__(self, "tools", None if tools is None else tuple(tools))


__all__ = ["Context"]
