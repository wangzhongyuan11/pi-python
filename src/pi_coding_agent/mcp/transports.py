"""Stdio JSON-RPC transport for MCP servers (P18-T01)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import cast

from pi_coding_agent.rpc.framing import JsonlFramer

from .contracts import InitializedServer, McpTransportError, ServerSpec

INITIALIZE_METHOD = "initialize"
PROTOCOL_VERSION = "2025-06-18"
HANDSHAKE_TIMEOUT = 30.0


class StdioTransport:
    """One JSON-RPC stdio connection to one MCP server process."""

    def __init__(self, spec: ServerSpec) -> None:
        self._spec = spec
        self._process: asyncio.subprocess.Process | None = None
        self._framer = JsonlFramer()
        self._pending: dict[int | str, asyncio.Future[dict[str, object]]] = {}
        self._read_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._stderr_tail: list[str] = []
        self._next_id = 0
        self._closed = False
        self.server_info: dict[str, object] = {}
        self.capabilities: dict[str, object] = {}

    @property
    def name(self) -> str:
        return self._spec.name

    async def start(self) -> InitializedServer:
        try:
            self._process = await asyncio.create_subprocess_exec(
                *self._spec.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as error:
            raise McpTransportError(
                f"failed to spawn MCP server {self._spec.name!r}: {error}", code="spawn"
            ) from error
        self._read_task = asyncio.create_task(self._read_loop())
        self._stderr_task = asyncio.create_task(self._drain_stderr())
        initialized = await self._request(
            INITIALIZE_METHOD,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "pi-python", "version": "1.0.0"},
            },
            timeout=HANDSHAKE_TIMEOUT,
        )
        result = initialized.get("result")
        if not isinstance(result, dict):
            raise McpTransportError(
                f"MCP server {self._spec.name!r} returned a malformed initialize reply",
                code="protocol",
            )
        info = result.get("serverInfo")
        self.server_info = cast("dict[str, object]", info if isinstance(info, dict) else {})
        caps = result.get("capabilities")
        self.capabilities = cast("dict[str, object]", caps if isinstance(caps, dict) else {})
        # Notify so the server enters its normal operating state.
        await self._notify("notifications/initialized", {})
        return InitializedServer(
            server_info=self.server_info,
            protocol_version=str(result.get("protocolVersion", PROTOCOL_VERSION)),
            capabilities=self.capabilities,
        )

    async def request(
        self, method: str, params: object, timeout: float | None = None
    ) -> dict[str, object]:
        reply = await self._request(method, params, timeout=timeout)
        if "error" in reply:
            error = reply["error"]
            raise McpTransportError(
                f"MCP {self._spec.name!r} {method} failed: "
                f"{error.get('message', json.dumps(error)) if isinstance(error, dict) else error}",
                code="server_error",
            )
        result = reply.get("result", {})
        return cast("dict[str, object]", result if isinstance(result, dict) else {})

    async def notify(self, method: str, params: object = None) -> None:
        await self._notify(method, params)

    async def _request(self, method: str, params: object, *, timeout: float) -> dict[str, object]:
        if self._closed or self._process is None or self._process.stdin is None:
            raise McpTransportError(f"MCP server {self._spec.name!r} is not running")
        self._next_id += 1
        request_id = self._next_id
        frame = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params if params is not None else {},
        }
        future: asyncio.Future[dict[str, object]] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        self._process.stdin.write((json.dumps(frame, ensure_ascii=False) + "\n").encode("utf-8"))
        try:
            await self._process.stdin.drain()
            limit = timeout if timeout is not None else self._spec.timeout_seconds
            return await asyncio.wait_for(future, limit)
        except TimeoutError as error:
            raise McpTransportError(
                f"MCP server {self._spec.name!r} {method} timed out", code="timeout"
            ) from error

    async def _notify(self, method: str, params: object) -> None:
        if self._closed or self._process is None or self._process.stdin is None:
            return
        frame = {"jsonrpc": "2.0", "method": method, "params": params if params is not None else {}}
        self._process.stdin.write((json.dumps(frame, ensure_ascii=False) + "\n").encode("utf-8"))
        await self._process.stdin.drain()

    async def _read_loop(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        while True:
            chunk = await self._process.stdout.read(8192)
            if not chunk:
                error = McpTransportError(
                    f"MCP server {self._spec.name!r} exited\n{self._stderr_tail_text()}",
                    code="disconnect",
                )
                for future in self._pending.values():
                    if not future.done():
                        future.set_exception(error)
                self._pending.clear()
                return
            for line in self._framer.feed(chunk):
                if not line.strip():
                    continue
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                request_id = message.get("id")
                future = self._pending.pop(request_id, None)
                if future is not None and not future.done():
                    future.set_result(message)

    async def _drain_stderr(self) -> None:
        assert self._process is not None and self._process.stderr is not None
        while True:
            chunk = await self._process.stderr.read(2048)
            if not chunk:
                return
            self._stderr_tail.extend(chunk.decode("utf-8", errors="replace").splitlines())
            del self._stderr_tail[:-50]

    def _stderr_tail_text(self) -> str:
        return "\n".join(self._stderr_tail[-10:])

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        process = self._process
        stdin = process.stdin if process is not None else None
        if process is not None and stdin is not None and process.returncode is None:
            try:
                stdin.close()
                await asyncio.wait_for(process.wait(), 5)
            except (TimeoutError, ConnectionResetError, RuntimeError, OSError):
                if process.returncode is None:
                    process.kill()
                try:
                    await process.wait()
                except ProcessLookupError:
                    pass
        if self._read_task is not None:
            self._read_task.cancel()
        if self._stderr_task is not None:
            self._stderr_task.cancel()
        error = McpTransportError(f"MCP server {self._spec.name!r} closed", code="disconnect")
        for future in self._pending.values():
            if not future.done():
                future.set_exception(error)
        self._pending.clear()


def create_stdio_transport(spec: ServerSpec) -> StdioTransport:
    """Build the stdio transport for one server spec."""

    _ = Path()  # keep pathlib import meaningful for parity with upstream layout
    return StdioTransport(spec)


__all__ = ["StdioTransport", "create_stdio_transport"]
