"""Async local RPC client with bounded events and independent request lifetimes."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import cast
from uuid import uuid4

from pydantic import ValidationError

from .framing import serialize_json_line
from .models import RpcCommand, RpcCommandType, RpcResponse, RpcSessionState

type Writer = Callable[[str], Awaitable[object]]
type Shutdown = Callable[[], Awaitable[None]]


class RpcClientError(RuntimeError):
    """A remote command failed or the RPC transport is no longer usable."""


class RpcClient:
    def __init__(
        self,
        reader: asyncio.StreamReader,
        write: Writer,
        *,
        shutdown: Shutdown | None = None,
        event_capacity: int = 256,
        request_timeout: float = 120,
    ) -> None:
        if event_capacity < 1 or request_timeout <= 0:
            raise ValueError("RPC capacity and timeout must be positive")
        self._reader = reader
        self._write = write
        self._shutdown = shutdown
        self._timeout = request_timeout
        self._events: asyncio.Queue[dict[str, object]] = asyncio.Queue(event_capacity)
        self._pending: dict[str, tuple[str, asyncio.Future[RpcResponse]]] = {}
        self._write_lock = asyncio.Lock()
        self._read_task: asyncio.Task[None] | None = None
        self._failure: RpcClientError | None = None
        self._failed = asyncio.Event()
        self._closed = False

    @classmethod
    async def launch(
        cls,
        argv: Sequence[str] | None = None,
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        request_timeout: float = 120,
        shutdown_timeout: float = 5,
    ) -> RpcClient:
        """Start a child without a shell; an explicit env replaces inherited env."""
        if shutdown_timeout <= 0 or request_timeout <= 0:
            raise ValueError("RPC timeouts must be positive")
        command = (
            tuple(argv)
            if argv is not None
            else (
                sys.executable,
                "-m",
                "pi_coding_agent",
                "--mode",
                "rpc",
            )
        )
        if not command:
            raise ValueError("RPC command must not be empty")
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=cwd,
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=4 * 1024 * 1024,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        assert process.stdin is not None and process.stdout is not None
        assert process.stderr is not None
        stdin = process.stdin
        stderr = process.stderr

        async def drain_stderr() -> None:
            # Never reflect arbitrary child logs (which can contain credentials)
            # in protocol exceptions; drain continuously to avoid pipe deadlock.
            while await stderr.read(8192):
                pass

        stderr_task = asyncio.create_task(drain_stderr())

        async def write(line: str) -> None:
            stdin.write(line.encode("utf-8"))
            await stdin.drain()

        async def shutdown() -> None:
            stdin.close()
            try:
                await asyncio.wait_for(process.wait(), shutdown_timeout)
            except TimeoutError:
                if process.returncode is None:
                    process.kill()
                await process.wait()
            finally:
                stderr_task.cancel()
                await asyncio.gather(stderr_task, return_exceptions=True)

        client = cls(process.stdout, write, shutdown=shutdown, request_timeout=request_timeout)
        await client.start()
        return client

    async def start(self) -> None:
        if self._closed or self._read_task is not None:
            raise RpcClientError("RPC client already started or closed")
        self._read_task = asyncio.create_task(self._read_loop())

    async def request(
        self,
        kind: RpcCommandType,
        *,
        timeout: float | None = None,
        **fields: object,
    ) -> object:
        self._ensure_open()
        command = RpcCommand.model_validate({**fields, "type": kind, "id": uuid4().hex})
        assert command.id is not None
        future: asyncio.Future[RpcResponse] = asyncio.get_running_loop().create_future()
        self._pending[command.id] = (kind, future)
        try:
            async with asyncio.timeout(self._timeout if timeout is None else timeout):
                await self._send(command.model_dump(by_alias=True, exclude_none=True))
                response = await future
            if not response.success:
                raise RpcClientError(response.error or "RPC command failed")
            return response.data
        finally:
            self._pending.pop(command.id, None)
            if not future.done():
                future.cancel()
            elif not future.cancelled():
                future.exception()

    async def get_state(self) -> RpcSessionState:
        return RpcSessionState.model_validate(await self.request("get_state"))

    async def prompt(self, message: str) -> None:
        await self.request("prompt", message=message)

    async def abort(self) -> None:
        await self.request("abort")

    async def respond_ui(
        self,
        request_id: str,
        *,
        value: str | None = None,
        confirmed: bool | None = None,
        cancelled: bool = False,
    ) -> None:
        if sum((value is not None, confirmed is not None, cancelled)) != 1:
            raise ValueError("UI response requires exactly one result")
        frame: dict[str, object] = {"type": "extension_ui_response", "id": request_id}
        if value is not None:
            frame["value"] = value
        elif confirmed is not None:
            frame["confirmed"] = confirmed
        else:
            frame["cancelled"] = True
        await self._send(frame)

    async def next_event(self) -> dict[str, object]:
        if not self._events.empty():
            return self._events.get_nowait()
        self._ensure_open()
        received = asyncio.create_task(self._events.get())
        failed = asyncio.create_task(self._failed.wait())
        try:
            await asyncio.wait((received, failed), return_when=asyncio.FIRST_COMPLETED)
            if received.done():
                return received.result()
            raise self._failure or RpcClientError("RPC client closed")
        finally:
            received.cancel()
            failed.cancel()
            await asyncio.gather(received, failed, return_exceptions=True)

    async def _send(self, frame: object) -> None:
        self._ensure_open()
        async with self._write_lock:
            self._ensure_open()
            try:
                await self._write(serialize_json_line(frame))
            except (OSError, RuntimeError):
                error = RpcClientError("RPC transport write failed")
                self._fail(error)
                raise error from None

    async def _read_loop(self) -> None:
        try:
            while line := await self._reader.readline():
                value: object = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("RPC frame must be an object")
                frame = cast("dict[str, object]", value)
                if frame.get("type") == "response":
                    response = RpcResponse.model_validate(frame)
                    if response.id is None:
                        raise ValueError("RPC response has no id")
                    pending = self._pending.get(response.id)
                    if pending is None:
                        continue  # A timed out or cancelled request can reply late.
                    kind, future = pending
                    if response.command != kind:
                        raise ValueError("RPC response command mismatch")
                    if not future.done():
                        future.set_result(response)
                else:
                    if not isinstance(frame.get("type"), str):
                        raise ValueError("RPC event has no type")
                    self._events.put_nowait(frame)
            self._fail(RpcClientError("RPC transport closed"))
        except asyncio.CancelledError:
            raise
        except (ValueError, UnicodeError, ValidationError, OSError, asyncio.QueueFull):
            self._fail(
                RpcClientError("RPC transport failed: invalid frame or event capacity exceeded")
            )

    def _ensure_open(self) -> None:
        if self._failure is not None:
            raise self._failure
        if self._closed or self._read_task is None:
            raise RpcClientError("RPC client not started or closed")

    def _fail(self, error: RpcClientError) -> None:
        if self._failure is None:
            self._failure = error
        self._failed.set()
        for _, future in self._pending.values():
            if not future.done():
                future.set_exception(self._failure)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._fail(RpcClientError("RPC client closed"))
        if self._read_task is not None:
            self._read_task.cancel()
            await asyncio.gather(self._read_task, return_exceptions=True)
        if self._shutdown is not None:
            await self._shutdown()

    async def __aenter__(self) -> RpcClient:
        if self._read_task is None:
            await self.start()
        return self

    async def __aexit__(self, *_error: object) -> None:
        await self.close()


__all__ = ["RpcClient", "RpcClientError"]
