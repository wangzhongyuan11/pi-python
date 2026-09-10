"""Serializable extension UI with correlated, cancellable client requests."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Literal
from uuid import uuid4

from pi_tui.protocols import NotificationLevel

type UiSender = Callable[[dict[str, object]], Awaitable[object]]


class RpcUiBridge:
    def __init__(
        self,
        send: UiSender,
        *,
        timeout_seconds: float = 120,
        capacity: int = 64,
    ) -> None:
        if timeout_seconds <= 0 or capacity < 1:
            raise ValueError("UI timeout and capacity must be positive")
        self._send = send
        self._timeout = timeout_seconds
        self._capacity = capacity
        self._closed = False
        self._pending: dict[str, tuple[str, asyncio.Future[object]]] = {}
        self._updates: set[asyncio.Task[object]] = set()

    async def select(self, title: str, options: tuple[str, ...]) -> str | None:
        value = await self._request("select", title=title, options=list(options))
        return value if isinstance(value, str) and value in options else None

    async def confirm(self, prompt: str) -> bool:
        return await self._request("confirm", title=prompt, message=prompt) is True

    async def input(self, prompt: str, *, default: str = "") -> str | None:
        value = await self._request("input", title=prompt, placeholder=default)
        return value if isinstance(value, str) else None

    async def editor(self, title: str, *, prefill: str = "") -> str | None:
        value = await self._request("editor", title=title, prefill=prefill)
        return value if isinstance(value, str) else None

    def notify(self, message: str, *, level: NotificationLevel = "info") -> None:
        self._update("notify", message=message, notifyType=level)

    def set_status(self, key: str, value: str | None) -> None:
        self._update("setStatus", statusKey=key, statusText=value)

    def set_widget(
        self,
        key: str,
        lines: tuple[str, ...] | None,
        *,
        placement: Literal["aboveEditor", "belowEditor"] = "aboveEditor",
    ) -> None:
        self._update(
            "setWidget",
            widgetKey=key,
            widgetLines=None if lines is None else list(lines),
            widgetPlacement=placement,
        )

    def set_title(self, title: str) -> None:
        self._update("setTitle", title=title)

    def set_editor_text(self, text: str) -> None:
        self._update("set_editor_text", text=text)

    def handle_response(self, frame: dict[str, object]) -> bool:
        if frame.get("type") != "extension_ui_response":
            return False
        request_id = frame.get("id")
        if not isinstance(request_id, str) or request_id not in self._pending:
            return False
        method, future = self._pending[request_id]
        if future.done():
            return False
        value: object
        if frame.get("cancelled") is True:
            value = None
        elif method == "confirm" and isinstance(frame.get("confirmed"), bool):
            value = frame["confirmed"]
        elif method != "confirm" and isinstance(frame.get("value"), str):
            value = frame["value"]
        else:
            return False
        future.set_result(value)
        return True

    async def _request(self, method: str, **payload: object) -> object:
        self._ensure_open()
        if len(self._pending) >= self._capacity:
            raise RuntimeError("too many pending UI requests")
        request_id = uuid4().hex
        future: asyncio.Future[object] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = (method, future)
        try:
            async with asyncio.timeout(self._timeout):
                await self._send(
                    {
                        "type": "extension_ui_request",
                        "id": request_id,
                        "method": method,
                        "timeout": int(self._timeout * 1000),
                        **payload,
                    }
                )
                return await future
        except TimeoutError:
            return None
        finally:
            self._pending.pop(request_id, None)
            if not future.done():
                future.cancel()

    def _update(self, method: str, **payload: object) -> None:
        self._ensure_open()
        # Synchronous UI methods cannot await transport backpressure. Keep their
        # outstanding sends bounded, and surface failures on the next call/flush.
        for task in tuple(self._updates):
            if task.done():
                self._updates.remove(task)
                task.result()
        if len(self._updates) >= self._capacity:
            raise RuntimeError("too many pending UI updates")
        self._updates.add(
            asyncio.create_task(
                self._send_update(
                    {
                        "type": "extension_ui_request",
                        "id": uuid4().hex,
                        "method": method,
                        **payload,
                    }
                )
            )
        )

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("RPC UI bridge is closed")

    async def _send_update(self, payload: dict[str, object]) -> object:
        return await self._send(payload)

    async def flush(self) -> None:
        tasks = tuple(self._updates)
        try:
            await asyncio.gather(*tasks)
        finally:
            self._updates.difference_update(tasks)

    async def close(self) -> None:
        self._closed = True
        for _, future in self._pending.values():
            if not future.done():
                future.set_result(None)
        self._pending.clear()
        # A disconnected client must not hold shutdown on a blocked write.
        tasks = tuple(self._updates)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._updates.clear()


__all__ = ["RpcUiBridge"]
