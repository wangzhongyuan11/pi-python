"""Async dialog bridge for extension UI requests with cancellation."""

from __future__ import annotations

import asyncio
import itertools
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DialogRequest:
    id: int
    text: str


class DialogBridge:
    """Pending extension dialogs; cancelling resolves the wait with None."""

    __slots__ = ("_counter", "_pending", "_requests")

    def __init__(self) -> None:
        self._counter = itertools.count(1)
        self._pending: dict[int, asyncio.Future[str | None]] = {}
        self._requests: dict[int, DialogRequest] = {}

    @property
    def pending(self) -> tuple[DialogRequest, ...]:
        return tuple(self._requests.values())

    async def show_dialog(self, text: str) -> str | None:
        request_id = next(self._counter)
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str | None] = loop.create_future()
        self._pending[request_id] = future
        self._requests[request_id] = DialogRequest(id=request_id, text=text)
        try:
            return await future
        finally:
            self._pending.pop(request_id, None)
            self._requests.pop(request_id, None)

    def respond(self, response: str, *, request_id: int | None = None) -> bool:
        if not self._pending:
            return False
        selected = next(iter(self._pending)) if request_id is None else request_id
        future = self._pending.pop(selected, None)
        if future is None:
            return False
        self._requests.pop(selected, None)
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
        self._requests.clear()
        return True


__all__ = ["DialogBridge", "DialogRequest"]
