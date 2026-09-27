"""Asynchronous core for the local stdio RPC product mode."""

from __future__ import annotations

import asyncio
import inspect
import json
import time
from collections.abc import Awaitable, Callable
from io import StringIO
from typing import TYPE_CHECKING, Protocol, cast

from pydantic import ValidationError

from pi_ai import TextContent, UserMessage

from ..agent_session_events import AgentSessionEventListener
from ..presenters import JsonEventPresenter
from .framing import serialize_json_line
from .models import RpcCommand, RpcResponse, parse_rpc_command

if TYPE_CHECKING:
    from .commands import RpcCommandAdapter
    from .ui_bridge import RpcUiBridge

type LineWriter = Callable[[str], object | Awaitable[object]]
type EventEncoder = Callable[[object], dict[str, object]]


class _RpcSession(Protocol):
    def subscribe(self, listener: AgentSessionEventListener) -> Callable[[], None]: ...
    async def prompt(self, message: str, /) -> None: ...
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
        await self._put(serialize_json_line(value))

    async def _put(self, line: str | None) -> None:
        if self._task is None:
            raise RuntimeError("RPC output is not started")
        if self._task.done():
            self._task.result()
            raise RuntimeError("RPC output is closed")
        try:
            self._queue.put_nowait(line)
        except asyncio.QueueFull:
            pending = asyncio.create_task(self._queue.put(line))
            try:
                await asyncio.wait((pending, self._task), return_when=asyncio.FIRST_COMPLETED)
                if self._task.done():
                    self._task.result()
                    raise RuntimeError("RPC output is closed")
                await pending
            finally:
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)

    async def close(self) -> None:
        if self._task is None:
            return
        try:
            await self._put(None)
            await self._task
        finally:
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
    __slots__ = (
        "_commands",
        "_encode_event",
        "_output",
        "_pending",
        "_session",
        "_ui",
        "_unsubscribe",
    )

    def __init__(
        self,
        *,
        session: _RpcSession,
        output: RpcOutput,
        event_encoder: EventEncoder | None = None,
        commands: RpcCommandAdapter | None = None,
        ui: RpcUiBridge | None = None,
    ) -> None:
        self._session = session
        self._output = output
        self._encode_event = event_encoder or _encode_agent_event
        self._commands = commands
        self._ui = ui
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
                if raw_type == "extension_ui_response":
                    if self._ui is not None:
                        self._ui.handle_response(mapping)
                    return
                raw_id = mapping.get("id")
                command_name = raw_type if isinstance(raw_type, str) else ""
                request_id = raw_id if isinstance(raw_id, str) else None
            command = parse_rpc_command(validated_input)
            await self._dispatch(command)
        except (
            json.JSONDecodeError,
            ValidationError,
            TypeError,
            ValueError,
            LookupError,
            RuntimeError,
        ) as error:
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

    async def close(self, *, abort: bool = False) -> None:
        if self._ui is not None:
            await self._ui.close()
        if abort:
            self._session.abort()
            tasks = tuple(self._pending)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        await self.wait_for_pending()
        self._unsubscribe()

    async def _dispatch(self, command: RpcCommand) -> None:
        if command.type == "prompt":
            await self._respond(_success(command))
            task = asyncio.create_task(self._run_prompt(command))
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
            handler(
                UserMessage(
                    content=(TextContent(text=command.message or ""),),
                    timestamp=time.time_ns() // 1_000_000,
                )
            )
            await self._respond(_success(command))
            return
        if self._commands is None:
            raise ValueError(f"unsupported RPC command: {command.type}")
        data = await self._commands.execute(command)
        if self._commands.session is not self._session:
            self._unsubscribe()
            self._session = self._commands.session
            self._unsubscribe = self._session.subscribe(self._on_event)
        from .commands import NO_DATA

        await self._respond(_success(command) if data is NO_DATA else _success(command, data))

    async def _run_prompt(self, command: RpcCommand) -> None:
        try:
            await self._session.prompt(command.message or "")
        except Exception as error:
            await self._respond(
                RpcResponse(
                    id=command.id,
                    command="prompt",
                    success=False,
                    error=str(error),
                )
            )

    async def _respond(self, response: RpcResponse) -> None:
        payload = response.model_dump(by_alias=True, exclude_none=True)
        if "data" in response.model_fields_set and response.data is None:
            payload["data"] = None
        await self._output.emit(payload)

    async def _on_event(self, event: object, _signal: asyncio.Event) -> None:
        await self._output.emit(self._encode_event(event))


_NO_DATA = object()


def _success(command: RpcCommand, data: object = _NO_DATA) -> RpcResponse:
    if data is _NO_DATA:
        return RpcResponse(id=command.id, command=command.type, success=True)
    return RpcResponse(id=command.id, command=command.type, success=True, data=data)


def _encode_agent_event(event: object) -> dict[str, object]:
    output = StringIO()
    JsonEventPresenter(output)(event, asyncio.Event())  # type: ignore[arg-type]
    return json.loads(output.getvalue())


__all__ = ["RpcOutput", "RpcServer"]
