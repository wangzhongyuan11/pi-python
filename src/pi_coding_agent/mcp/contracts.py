"""MCP server transport contracts (P18-T01).

One transport per server: JSON-RPC 2.0 over stdio, the initialize handshake,
correlated request/response, structured lifecycle errors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


class McpTransportError(RuntimeError):
    """A transport-level failure (spawn, protocol, or disconnect)."""

    def __init__(self, message: str, *, code: str = "transport") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ServerSpec:
    """Connection definition for one MCP server."""

    kind: Literal["stdio"] = "stdio"
    name: str = ""
    command: list[str] = field(default_factory=list)
    env: dict[str, str] | None = None
    timeout_seconds: float = 60.0

    def __post_init__(self) -> None:
        if self.kind == "stdio" and not self.command:
            raise ValueError("stdio server requires a command")


@dataclass(frozen=True, slots=True)
class InitializedServer:
    server_info: dict[str, object]
    protocol_version: str
    capabilities: dict[str, object]


__all__ = ["InitializedServer", "McpTransportError", "ServerSpec"]
