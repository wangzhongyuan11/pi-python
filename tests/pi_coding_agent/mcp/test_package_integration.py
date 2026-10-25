"""P18-T05: package-declared MCP servers stay consistent with host state."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from pi_coding_agent.extensions.api import ExtensionAPI
from pi_coding_agent.extensions.registry import RegistryConflictError
from pi_coding_agent.mcp.host import McpHost
from pi_coding_agent.mcp.packages import (
    McpHostManager,
    PackageMcpError,
    read_package_mcp_servers,
)

from tests.pi_coding_agent.mcp.helpers import write_echo_server


def _package_with_server(tmp_path: Path) -> Path:
    root = tmp_path / "echo-package"
    root.mkdir()
    server_spec = write_echo_server(root)
    (root / "package.json").write_text(
        json.dumps(
            {
                "name": "echo-package",
                "pi": {
                    "mcpServers": {
                        "echo": {
                            "command": server_spec.command,
                            "timeoutSeconds": 5,
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return root


def test_package_manifest_yields_sorted_server_specs(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "name": "multi",
                "pi": {
                    "mcpServers": {
                        "zeta": {"command": ["z"], "env": {"K": "V"}},
                        "alpha": {"command": ["a"], "timeoutSeconds": 9},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    specs = read_package_mcp_servers(tmp_path)

    assert [spec.name for spec in specs] == ["alpha", "zeta"]
    assert specs[0].command == ["a"]
    assert specs[0].timeout_seconds == 9.0
    assert specs[1].env == {"K": "V"}


def test_package_without_mcp_declaration_yields_nothing(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "plain", "pi": {"skills": "./skills"}}),
        encoding="utf-8",
    )

    assert read_package_mcp_servers(tmp_path) == ()


def test_invalid_mcp_declaration_raises_package_error(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"pi": {"mcpServers": {"broken": {}}}}),
        encoding="utf-8",
    )

    with pytest.raises(PackageMcpError):
        read_package_mcp_servers(tmp_path)


def test_extension_api_registers_mcp_servers() -> None:
    api = ExtensionAPI("myext")

    api.define_mcp_server("docs", {"command": ["docs-mcp"]})

    registration = api.registry.lookup("mcp_server", "docs")
    assert registration is not None
    assert registration.source == "myext"
    assert registration.payload == {"command": ["docs-mcp"]}


def test_conflicting_mcp_server_registration_raises() -> None:
    first = ExtensionAPI("one")
    second = ExtensionAPI("two", registry=first.registry)

    first.define_mcp_server("docs", {"command": ["a"]})

    with pytest.raises(RegistryConflictError, match="already registered"):
        second.define_mcp_server("docs", {"command": ["b"]})


def test_adapter_install_restart_remove_matches_host(tmp_path: Path) -> None:
    package_root = _package_with_server(tmp_path)

    async def scenario() -> tuple[bool, bool, bool, bool, bool]:
        host = McpHost()
        manager = McpHostManager(host)
        specs = await manager.install(package_root)
        installed_names = manager.names
        config = manager.config("echo")
        tools_before = await host.list_tools()
        await manager.restart("echo")
        tools_after_restart = await host.list_tools()
        restart_counted = host.restart_counts.get("echo", 0) >= 1
        await manager.remove("echo")
        tools_removed = await host.list_tools()
        still_installed = manager.config("echo") is not None
        await host.close()
        return (
            [spec.name for spec in specs] == ["echo"],
            installed_names == ("echo",),
            config is not None and config.timeout_seconds == 5.0,
            "echo_tool" in [tool.get("name") for tool in tools_before]
            and "echo_tool" in [tool.get("name") for tool in tools_after_restart]
            and restart_counted,
            "echo_tool" not in [tool.get("name") for tool in tools_removed]
            and not still_installed,
        )

    (
        specs_ok,
        names_ok,
        config_ok,
        lifecycle_ok,
        removed_ok,
    ) = asyncio.run(scenario())
    assert specs_ok
    assert names_ok
    assert config_ok
    assert lifecycle_ok
    assert removed_ok
