"""McpHost: owns the lifecycle of every configured MCP server (P18-T02).

Boots servers, detects crashes, restarts within a capped budget, exposes
merged tool listings and tool calls, and tears everything down on close.
"""

from __future__ import annotations

import asyncio

from .contracts import McpTransportError, ServerSpec
from .transports import StdioTransport, create_stdio_transport

DEFAULT_RESTART_CAP = 3
DEFAULT_RESTART_DELAY = 0.2
_WATCH_POLL_SECONDS = 0.2


class _ManagedServer:
    def __init__(self, spec: ServerSpec) -> None:
        self.spec = spec
        self.transport: StdioTransport | None = None
        self.restart_count = 0
        self.last_error: str | None = None

    def process_dead(self) -> bool:
        return (
            self.transport is not None
            and self.transport._process is not None
            and self.transport._process.returncode is not None
        )


class McpHost:
    """Own every configured MCP server for one product generation."""

    def __init__(
        self,
        *,
        restart_cap: int = DEFAULT_RESTART_CAP,
        restart_delay: float = DEFAULT_RESTART_DELAY,
    ) -> None:
        self._servers: dict[str, _ManagedServer] = {}
        self._restart_cap = restart_cap
        self._restart_delay = restart_delay
        self.restart_counts: dict[str, int] = {}
        self._watchers: set[asyncio.Task[None]] = set()
        self._closed = False

    async def start(self, specs: list[ServerSpec]) -> None:
        if self._closed:
            return
        for spec in specs:
            server = _ManagedServer(spec)
            self._servers[spec.name] = server
            await self._boot(server)
            self._spawn_watchdog(server)

    def _spawn_watchdog(self, server: _ManagedServer) -> None:
        async def watch() -> None:
            while not self._closed:
                await asyncio.sleep(_WATCH_POLL_SECONDS)
                if self._closed:
                    return
                if server.process_dead():
                    server.last_error = "server crashed"
                    await self._restart(server)
                    return

        task = asyncio.create_task(watch())
        self._watchers.add(task)
        task.add_done_callback(self._watchers.discard)

    async def _boot(self, server: _ManagedServer) -> None:
        transport = create_stdio_transport(server.spec)
        server.transport = transport
        try:
            await transport.start()
            server.last_error = None
        except McpTransportError as error:
            server.last_error = str(error)
            server.transport = None
            raise

    async def _restart(self, server: _ManagedServer) -> None:
        name = server.spec.name
        count = self.restart_counts.get(name, 0) + 1
        self.restart_counts[name] = count
        if count > self._restart_cap:
            server.last_error = f"restart cap {self._restart_cap} reached"
            return
        await asyncio.sleep(self._restart_delay)
        if self._closed:
            return
        await self._boot(server)
        self._spawn_watchdog(server)

    @property
    def failed_servers(self) -> set[str]:
        """Servers whose process died and have not been revived yet."""

        return {
            name
            for name, server in self._servers.items()
            if server.transport is None or server.process_dead()
        }

    async def ensure_running(self, name: str) -> None:
        """Force a restart when the server's process has died (cap still applies)."""

        server = self._servers.get(name)
        if server is None or self._closed:
            return
        if server.transport is not None and not server.process_dead():
            return
        if server.transport is not None:
            await server.transport.close()
            server.transport = None
        await self._restart(server)

    async def list_tools(self) -> list[dict[str, object]]:
        listing: list[dict[str, object]] = []
        for server in self._servers.values():
            await self.ensure_running(server.spec.name)
            if server.transport is None:
                continue
            result = await server.transport.request("tools/list", {})
            for tool in result.get("tools", []) or []:
                entry = dict(tool)
                entry["server"] = server.spec.name
                listing.append(entry)
        return listing

    async def call_tool(
        self, server_name: str, tool_name: str, arguments: dict[str, object]
    ) -> dict[str, object]:
        await self.ensure_running(server_name)
        server = self._servers.get(server_name)
        if server is None or server.transport is None:
            raise McpTransportError(f"MCP server {server_name!r} is not running")
        return await server.transport.request(
            "tools/call", {"name": tool_name, "arguments": arguments}
        )

    async def close(self) -> None:
        self._closed = True
        for watcher in self._watchers:
            watcher.cancel()
        for server in self._servers.values():
            if server.transport is not None:
                try:
                    await server.transport.close()
                except ProcessLookupError:
                    pass
                # Keep the closed transport attached so callers can inspect
                # the final exit status after close().
        self._servers.clear()
