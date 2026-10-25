"""Package-declared MCP servers and a manager keeping host state aligned (P18-T05)."""

from __future__ import annotations

import json
from pathlib import Path

from .contracts import ServerSpec
from .host import McpHost


class PackageMcpError(ValueError):
    """A package's MCP declaration is missing, malformed, or invalid."""


def read_package_mcp_servers(package_root: Path) -> tuple[ServerSpec, ...]:
    """Read ``package.json#pi.mcpServers`` declarations as sorted ServerSpecs."""

    manifest_path = package_root / "package.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PackageMcpError(f"cannot read MCP manifest: {manifest_path}") from error
    if not isinstance(manifest, dict):
        raise PackageMcpError(f"MCP manifest must be an object: {manifest_path}")
    pi_section = manifest.get("pi")
    servers = pi_section.get("mcpServers") if isinstance(pi_section, dict) else None
    if servers is None:
        return ()
    if not isinstance(servers, dict):
        raise PackageMcpError("pi.mcpServers must be an object")

    specs: list[ServerSpec] = []
    for raw_name, raw_config in servers.items():
        name = str(raw_name)
        if not name:
            raise PackageMcpError("MCP server names must be non-empty")
        if not isinstance(raw_config, dict):
            raise PackageMcpError(f"MCP server {name!r} config must be an object")
        command = raw_config.get("command")
        if (
            not isinstance(command, list)
            or not command
            or not all(isinstance(item, str) and item for item in command)
        ):
            raise PackageMcpError(f"MCP server {name!r} requires a non-empty command list")
        env = raw_config.get("env")
        if env is not None:
            if not isinstance(env, dict) or not all(
                isinstance(key, str) and isinstance(value, str) for key, value in env.items()
            ):
                raise PackageMcpError(f"MCP server {name!r} env must map strings to strings")
            env = dict(env)
        timeout = raw_config.get("timeoutSeconds", 60.0)
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
            raise PackageMcpError(f"MCP server {name!r} timeoutSeconds must be positive")
        specs.append(
            ServerSpec(
                name=name,
                command=[str(item) for item in command],
                env=env,
                timeout_seconds=float(timeout),
            )
        )
    return tuple(sorted(specs, key=lambda spec: spec.name))


class McpHostManager:
    """Install, restart, and remove package MCP servers through one McpHost."""

    def __init__(self, host: McpHost) -> None:
        self._host = host
        self._installed: dict[str, ServerSpec] = {}

    async def install(self, package_root: Path) -> tuple[ServerSpec, ...]:
        specs = read_package_mcp_servers(package_root)
        await self._host.start(list(specs))
        for spec in specs:
            self._installed[spec.name] = spec
        return specs

    def config(self, name: str) -> ServerSpec | None:
        return self._installed.get(name)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._installed))

    @property
    def failed(self) -> set[str]:
        return self._host.failed_servers

    async def restart(self, name: str) -> None:
        await self._host.restart(name)

    async def remove(self, name: str) -> None:
        self._installed.pop(name, None)
        await self._host.remove(name)


__all__ = ["McpHostManager", "PackageMcpError", "read_package_mcp_servers"]
