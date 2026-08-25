"""Async dialog bridge for extension UI requests with cancellation."""

from __future__ import annotations

import asyncio
import itertools


class DialogBridge:
    """Pending extension dialogs; cancelling resolves the wait with None."""

    __slots__ = ("_counter", "_pending")

    def __init__(self) -> None:
        self._counter = itertools.count(1)
        self._pending: dict[int, asyncio.Future[str | None]] = {}

    async def show_dialog(self, text: str) -> str | None:
        request_id = next(self._counter)
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str | None] = loop.create_future()
        self._pending[request_id] = future
        try:
            return await future
        finally:
            self._pending.pop(request_id, None)

    def respond(self, response: str) -> bool:
        if not self._pending:
            return False
        request_id = next(iter(self._pending))
        future = self._pending.pop(request_id)
        if not future.done():
            future.set_result(response)
        return True

    def cancel_pending(self) -> bool:
        if not self._pending:
            return False
        for future in list(self._pending.values()):
            if not future.done():
                future.set_result(None)
        self._pending.clear()
        return True


__all__ = ["DialogBridge"]
