"""Session selector actions wired to the AgentSession runtime."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..session.catalog import open_session
from ..session.manager import SessionManager


class _Summary(Protocol):
    path: Path


class RuntimeLike(Protocol):
    async def switch(self, manager: SessionManager) -> None: ...

    async def fork(self, manager: SessionManager) -> None: ...


@dataclass(frozen=True, slots=True)
class Selection:
    index: int
    item: _SummaryLike | None


class _SummaryLike(Protocol):
    path: Path


class _NamedItem(Protocol):
    name: str


class SessionSelector:
    """Clamped list navigation over catalog summaries or arbitrary named items."""

    __slots__ = ("_index", "_items")

    def __init__(self, items: Sequence[_NamedItem]) -> None:
        self._items: tuple[_NamedItem, ...] = tuple(items)
        self._index = 0

    @property
    def index(self) -> int:
        return self._index

    @property
    def highlighted(self) -> _NamedItem | None:
        if not self._items:
            return None
        return self._items[self._index]

    def down(self) -> None:
        self._index = min(self._index + 1, max(0, len(self._items) - 1))

    def up(self) -> None:
        self._index = max(self._index - 1, 0)

    def confirm(self) -> _NamedItem | None:
        return self.highlighted

    def cancel(self) -> None:
        return None


async def switch_to(runtime: RuntimeLike, summary: _Summary) -> None:
    manager = await asyncio.to_thread(open_session, summary.path)
    manager = manager if isinstance(manager, SessionManager) else manager  # type: ignore[assignment]
    await runtime.switch(manager)


async def fork_from(runtime: RuntimeLike, summary: _Summary) -> None:
    manager = await asyncio.to_thread(open_session, summary.path)
    await runtime.fork(manager)


__all__ = ["RuntimeLike", "Selection", "SessionSelector", "fork_from", "switch_to"]
