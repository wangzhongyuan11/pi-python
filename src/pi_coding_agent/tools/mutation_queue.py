"""Per-real-path serialization for file mutation tools."""

from __future__ import annotations

import asyncio
import threading
import weakref
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from .paths import canonical_tool_path

T = TypeVar("T")


@dataclass(slots=True)
class _Entry:
    lock: asyncio.Lock
    users: int = 0


class FileMutationQueue:
    def __init__(self) -> None:
        self._registry_lock = asyncio.Lock()
        self._entries: dict[Path, _Entry] = {}

    async def run(
        self,
        path: str | Path,
        *,
        cwd: Path,
        operation: Callable[[], Awaitable[T]],
    ) -> T:
        key = canonical_tool_path(path, cwd=cwd)
        async with self._registry_lock:
            entry = self._entries.setdefault(key, _Entry(lock=asyncio.Lock()))
            entry.users += 1

        acquired = False
        try:
            await entry.lock.acquire()
            acquired = True
            return await operation()
        finally:
            if acquired:
                entry.lock.release()
            async with self._registry_lock:
                entry.users -= 1
                if entry.users == 0 and self._entries.get(key) is entry:
                    del self._entries[key]


_DEFAULT_QUEUES_LOCK = threading.Lock()
_DEFAULT_QUEUES: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, FileMutationQueue] = (
    weakref.WeakKeyDictionary()
)


def default_mutation_queue() -> FileMutationQueue:
    loop = asyncio.get_running_loop()
    with _DEFAULT_QUEUES_LOCK:
        queue = _DEFAULT_QUEUES.get(loop)
        if queue is None:
            queue = FileMutationQueue()
            _DEFAULT_QUEUES[loop] = queue
        return queue


__all__ = ["FileMutationQueue", "default_mutation_queue"]
