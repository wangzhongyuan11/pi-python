from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
from pydantic import BaseModel

from pi_agent import AgentTool, AgentToolResult
from pi_ai import TextContent
from pi_coding_agent.builtin_extensions.permission_gate import (
    PermissionDeniedError,
    PermissionGate,
)
from pi_coding_agent.builtin_extensions.powershell import PowerShellExtension
from pi_coding_agent.tools.operations import OutputSink


def test_permission_gate_is_disabled_by_default_and_never_prompts() -> None:
    prompts: list[str] = []

    def record(tool: str) -> bool:
        prompts.append(tool)
        return True

    gate = PermissionGate(confirmer=record)

    decision = gate.decide("bash")

    assert decision.allowed is True
    assert prompts == []


def test_enabled_gate_denies_when_confirmer_declines() -> None:
    def deny(_tool: str) -> bool:
        return False

    gate = PermissionGate(enabled=True, confirmer=deny)

    decision = gate.decide("write")

    assert decision.allowed is False
    assert decision.tool == "write"


def test_enabled_gate_asks_confirmer_per_tool() -> None:
    asked: list[str] = []

    def confirm(tool: str) -> bool:
        asked.append(tool)
        return tool != "edit"

    gate = PermissionGate(enabled=True, confirmer=confirm)

    assert gate.decide("read").allowed is True
    assert gate.decide("edit").allowed is False
    assert asked == ["read", "edit"]


def test_enabled_gate_wraps_real_tools_before_execution() -> None:
    class Input(BaseModel):
        value: str

    called = False

    async def execute(*_args: object) -> AgentToolResult[None]:
        nonlocal called
        called = True
        return AgentToolResult(content=(TextContent(text="ran"),), details=None)

    tool = AgentTool(
        name="write",
        label="write",
        description="write",
        parameter_type=Input,
        execute=execute,
    )
    wrapped = PermissionGate(enabled=True, confirmer=lambda _name: False).wrap_tool(tool)

    with pytest.raises(PermissionDeniedError):
        asyncio.run(wrapped.execute("call", Input(value="x")))
    assert called is False


def test_powershell_is_windows_only_and_opt_in() -> None:
    extension = PowerShellExtension()

    assert extension.enabled is False

    linux = PowerShellExtension(platform="linux")
    linux.enable()

    assert linux.available is False

    windows = PowerShellExtension(platform="win32")
    assert windows.available is False
    windows.enable()

    assert windows.enabled is True
    assert windows.available is True


def test_powershell_extension_provides_bounded_agent_tool(tmp_path: Path) -> None:
    class Processes:
        def __init__(self) -> None:
            self.argv: tuple[str, ...] = ()

        async def run(
            self,
            argv: Sequence[str],
            *,
            cwd: Path,
            environment: Mapping[str, str] | None,
            stdin: bytes | None,
            stdout: OutputSink,
            stderr: OutputSink,
            timeout: float | None,
            abort_event: asyncio.Event | None,
        ) -> int:
            del cwd, environment, stdin, stderr, timeout, abort_event
            self.argv = tuple(argv)
            await stdout(b"ok")
            return 0

    processes = Processes()
    extension = PowerShellExtension(platform="win32")
    extension.enable()
    tool = extension.create_tool(cwd=tmp_path, operations=processes)

    result = asyncio.run(
        tool.execute("call", tool.parameter_type(command="Get-Location", timeout=None))
    )

    assert processes.argv[-2:] == ("-Command", "Get-Location")
    assert result.content == (TextContent(text="ok"),)
