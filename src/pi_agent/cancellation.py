"""Run-scoped cancellation and late-update filtering."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RunCancellation:
    generation: int
    abort_event: asyncio.Event
    done_event: asyncio.Event


async def _wait_for_run(run: RunCancellation | None) -> None:
    if run is not None:
        await run.done_event.wait()


class CancellationController:
    """Own one active run and reject updates from aborted or older runs."""

    __slots__ = ("_active", "_generation")

    def __init__(self) -> None:
        self._active: RunCancellation | None = None
        self._generation = 0

    @property
    def signal(self) -> asyncio.Event | None:
        return self._active.abort_event if self._active is not None else None

    def begin(self) -> RunCancellation:
        if self._active is not None:
            raise RuntimeError("A run is already active")
        self._generation += 1
        self._active = RunCancellation(self._generation, asyncio.Event(), asyncio.Event())
        return self._active

    def abort(self) -> None:
        if self._active is not None:
            self._active.abort_event.set()

    def accepts(self, run: RunCancellation) -> bool:
        return self._active is run

    def accepts_update(self, run: RunCancellation) -> bool:
        return self.accepts(run) and not run.abort_event.is_set()

    def wait_for_idle(self) -> Coroutine[Any, Any, None]:
        return _wait_for_run(self._active)

    def finish(self, run: RunCancellation) -> None:
        if self._active is run:
            run.done_event.set()
            self._active = None


__all__ = ["CancellationController", "RunCancellation"]
