"""P18-T06: prove the MCP product integration end to end.

Full lifecycle over the real composition path (create_agent_session):
package-configured servers, tool calls, crash recovery, abort safety,
server switching, and clean exit.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

from pi_ai import FakeProvider, ToolCall, fake_assistant_message
from pi_coding_agent.mcp.host import McpHost
from pi_coding_agent.mcp.packages import McpHostManager
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.sdk import CreateAgentSessionOptions, create_agent_session

REPO = Path(__file__).resolve().parents[3]
MCP_FIXTURE = REPO / "tests" / "fixtures" / "mcp_server"


def _materialize_package(
    tmp_path: Path,
    *,
    server_name: str = "echo",
    env: dict[str, str] | None = None,
) -> Path:
    """Copy the fixture echo package into tmp with the command resolved."""

    package_root = tmp_path / f"{server_name}-package"
    package_root.mkdir()
    script = package_root / "echo_server.py"
    script.write_text(
        (MCP_FIXTURE / "echo_server.py").read_text(encoding="utf-8"), encoding="utf-8"
    )
    manifest = json.loads((MCP_FIXTURE / "package.json").read_text(encoding="utf-8"))
    raw_command = manifest["pi"]["mcpServers"]["echo"]["command"]
    command = [
        sys.executable if item == "{{PYTHON}}" else str(package_root / item)
        for item in raw_command
    ]
    entry: dict[str, object] = {"command": command, "timeoutSeconds": 10}
    if env is not None:
        entry["env"] = env
    manifest["name"] = f"{server_name}-mcp-package"
    manifest["pi"]["mcpServers"] = {server_name: entry}
    (package_root / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
    return package_root


def _runtime(*responses: object) -> ModelRuntime:
    provider = FakeProvider(list(responses))
    return ModelRuntime(provider=provider, model=provider.models[0])


def _options(tmp_path: Path, host: McpHost, runtime: ModelRuntime) -> CreateAgentSessionOptions:
    return CreateAgentSessionOptions(cwd=tmp_path, model_runtime=runtime, mcp_host=host)


def _tool_use(name: str, text: str, call_id: str) -> object:
    return fake_assistant_message(
        ToolCall(id=call_id, name=name, arguments={"text": text}), stop_reason="toolUse"
    )


def _transcript(session: object) -> str:
    return "\n".join(
        block.text
        for message in session.messages  # type: ignore[attr-defined]
        for block in getattr(message, "content", ()) or ()
        if getattr(block, "type", "") == "text"
    )


def test_package_session_calls_tool_and_exits_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PI_PYTHON_AGENT_DIR", str(tmp_path / "agent"))
    package_root = _materialize_package(tmp_path)

    async def scenario() -> tuple[str, int | None, bool]:
        host = McpHost()
        manager = McpHostManager(host)
        await manager.install(package_root)
        runtime = _runtime(
            _tool_use("mcp_search", "echo", "s1"),
            _tool_use("echo_tool", "hello", "s2"),
            fake_assistant_message("done"),
        )
        created = await create_agent_session(_options(tmp_path, host, runtime))
        try:
            await created.session.prompt("call the echo tool")
            transcript = _transcript(created.session)
            process = host._servers["echo"].transport._process
        finally:
            await created.close()
            await host.close()
        return transcript, process.returncode, manager.names == ("echo",)

    transcript, returncode, names_intact = asyncio.run(scenario())
    assert "echo:hello" in transcript
    assert returncode is not None
    assert names_intact


def test_crashed_server_recovers_within_product_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PI_PYTHON_AGENT_DIR", str(tmp_path / "agent"))
    package_root = _materialize_package(tmp_path, env={"ECHO_CRASH_AFTER_CALLS": "1"})

    async def scenario() -> tuple[str, int]:
        host = McpHost()
        manager = McpHostManager(host)
        await manager.install(package_root)
        runtime = _runtime(
            _tool_use("mcp_search", "echo", "s0"),
            _tool_use("echo_tool", "one", "s1"),
            _tool_use("echo_tool", "two", "s2"),
            fake_assistant_message("done"),
        )
        created = await create_agent_session(_options(tmp_path, host, runtime))
        try:
            await created.session.prompt("call echo twice")
            transcript = _transcript(created.session)
        finally:
            await created.close()
            await host.close()
        return transcript, host.restart_counts.get("echo", 0)

    transcript, restarts = asyncio.run(scenario())
    assert "echo:one" in transcript
    assert "echo:two" in transcript
    assert restarts >= 1


def test_abort_keeps_host_usable_then_clean_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PI_PYTHON_AGENT_DIR", str(tmp_path / "agent"))
    package_root = _materialize_package(tmp_path)

    async def scenario() -> tuple[str, int | None]:
        host = McpHost()
        manager = McpHostManager(host)
        await manager.install(package_root)
        runtime = _runtime(
            fake_assistant_message("first"), fake_assistant_message("second")
        )
        created = await create_agent_session(_options(tmp_path, host, runtime))
        try:
            await created.session.prompt("hello")
            created.session.abort()
            await created.session.prompt("again")
            transcript = _transcript(created.session)
            process = host._servers["echo"].transport._process
        finally:
            await created.close()
            await host.close()
        return transcript, process.returncode

    transcript, returncode = asyncio.run(scenario())
    assert "first" in transcript and "second" in transcript
    assert returncode is not None


def test_switch_package_servers_between_sessions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PI_PYTHON_AGENT_DIR", str(tmp_path / "agent"))
    first_root = _materialize_package(tmp_path, server_name="echo")
    second_root = _materialize_package(tmp_path, server_name="echo2")

    async def scenario() -> tuple[bool, set[str], set[str], tuple[str, ...], bool]:
        host = McpHost()
        manager = McpHostManager(host)
        await manager.install(first_root)
        runtime = _runtime(fake_assistant_message("ok"))
        first = await create_agent_session(_options(tmp_path, host, runtime))
        first_has_search = "mcp_search" in [
            tool.name for tool in first.session.agent.state.tools
        ]
        await first.close()
        servers_before = {str(entry.get("server")) for entry in await host.list_tools()}
        await manager.remove("echo")
        await manager.install(second_root)
        servers_after = {str(entry.get("server")) for entry in await host.list_tools()}
        second = await create_agent_session(_options(tmp_path, host, runtime))
        second_has_search = "mcp_search" in [
            tool.name for tool in second.session.agent.state.tools
        ]
        await second.close()
        await host.close()
        return first_has_search, servers_before, servers_after, manager.names, second_has_search

    (
        first_has_search,
        servers_before,
        servers_after,
        names,
        second_has_search,
    ) = asyncio.run(scenario())
    assert first_has_search
    assert second_has_search
    assert servers_before == {"echo"}
    assert servers_after == {"echo2"}
    assert names == ("echo2",)
