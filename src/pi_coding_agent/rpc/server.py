"""Asynchronous core for the local stdio RPC product mode."""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Awaitable, Callable
from io import StringIO
from typing import Protocol, cast

from pydantic import ValidationError

from ..presenters import JsonEventPresenter
from .framing import serialize_json_line
from .models import RpcCommand, RpcResponse, parse_rpc_command

type LineWriter = Callable[[str], object | Awaitable[object]]
type EventEncoder = Callable[[object], dict[str, object]]


class _RpcSession(Protocol):
    def subscribe(self, listener: Callable[..., object]) -> Callable[[], None]: ...
    async def prompt(self, message: str) -> None: ...
    def abort(self) -> None: ...


class RpcOutput:
    """Single bounded writer so slow consumers exert protocol backpressure."""

    __slots__ = ("_capacity", "_queue", "_task", "_write")

    def __init__(self, write: LineWriter, *, capacity: int = 64) -> None:
        if capacity < 1:
            raise ValueError("RPC output capacity must be positive")
        self._write = write
        self._capacity = capacity
        self._queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=capacity)
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def emit(self, value: object) -> None:
        if self._task is None:
            raise RuntimeError("RPC output is not started")
        await self._queue.put(serialize_json_line(value))

    async def close(self) -> None:
        if self._task is None:
            return
        await self._queue.join()
        await self._queue.put(None)
        await self._task
        self._task = None

    async def _run(self) -> None:
        while True:
            line = await self._queue.get()
            try:
                if line is None:
                    return
                result = self._write(line)
                if inspect.isawaitable(result):
                    await result
            finally:
                self._queue.task_done()


class RpcServer:
    __slots__ = ("_encode_event", "_output", "_pending", "_session", "_unsubscribe")

    def __init__(
        self,
        *,
        session: _RpcSession,
        output: RpcOutput,
        event_encoder: EventEncoder | None = None,
    ) -> None:
        self._session = session
        self._output = output
        self._encode_event = event_encoder or _encode_agent_event
        self._pending: set[asyncio.Task[None]] = set()
        self._unsubscribe = session.subscribe(self._on_event)

    async def handle_line(self, line: str) -> None:
        command_name = ""
        request_id: str | None = None
        try:
            value: object = json.loads(line)
            validated_input: object = value
            if isinstance(value, dict):
                mapping = cast("dict[str, object]", value)
                validated_input = mapping
                raw_type = mapping.get("type")
                raw_id = mapping.get("id")
                command_name = raw_type if isinstance(raw_type, str) else ""
                request_id = raw_id if isinstance(raw_id, str) else None
            command = parse_rpc_command(validated_input)
            await self._dispatch(command)
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as error:
            await self._respond(
                RpcResponse(
                    id=request_id,
                    command=command_name,
                    success=False,
                    error=str(error),
                )
            )

    async def wait_for_pending(self) -> None:
        if self._pending:
            await asyncio.gather(*tuple(self._pending))

    async def close(self) -> None:
        await self.wait_for_pending()
        self._unsubscribe()

    async def _dispatch(self, command: RpcCommand) -> None:
        if command.type == "prompt":
            await self._respond(_success(command))
            task = asyncio.create_task(self._session.prompt(command.message or ""))
            self._pending.add(task)
            task.add_done_callback(self._pending.discard)
            return
        if command.type == "abort":
            self._session.abort()
            await self._respond(_success(command))
            return
        if command.type in {"steer", "follow_up"}:
            agent = getattr(self._session, "agent", None)
            handler = getattr(agent, command.type, None)
            if not callable(handler):
                raise ValueError(f"{command.type} is unavailable")
            handler(command.message)
            await self._respond(_success(command))
            return
        raise ValueError(f"unsupported RPC command: {command.type}")

    async def _respond(self, response: RpcResponse) -> None:
        await self._output.emit(response.model_dump(by_alias=True, exclude_none=True))

    async def _on_event(self, event: object, _signal: asyncio.Event) -> None:
        await self._output.emit(self._encode_event(event))


def _success(command: RpcCommand, data: object | None = None) -> RpcResponse:
    return RpcResponse(id=command.id, command=command.type, success=True, data=data)


def _encode_agent_event(event: object) -> dict[str, object]:
    output = StringIO()
    JsonEventPresenter(output)(event, asyncio.Event())  # type: ignore[arg-type]
    return json.loads(output.getvalue())


__all__ = ["RpcOutput", "RpcServer"]
