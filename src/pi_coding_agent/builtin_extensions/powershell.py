"""Opt-in PowerShell tool provider, available only on Windows."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from pi_agent import AgentTool, AgentToolResult, AgentToolUpdateCallback
from pi_ai import JsonValue, TextContent

from ..tools.bash import execute_bash
from ..tools.bash_resolver import BashConfig
from ..tools.operations import ProcessOperations


class PowerShellInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    command: str
    timeout: float | None = None


class PowerShellToolError(RuntimeError):
    pass


class PowerShellExtension:
    """Disabled by default; usable only when the platform is Windows."""

    __slots__ = ("_enabled", "_executable", "_platform")

    def __init__(self, *, platform: str | None = None, executable: str = "powershell.exe") -> None:
        self._platform = platform if platform is not None else sys.platform
        self._executable = executable
        self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def available(self) -> bool:
        return self._enabled and self._platform == "win32"

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False

    def create_tool(
        self,
        *,
        cwd: Path,
        operations: ProcessOperations | None = None,
    ) -> AgentTool[PowerShellInput, dict[str, JsonValue]]:
        if not self.available:
            raise RuntimeError("PowerShell extension is unavailable until enabled on Windows")
        config = BashConfig(
            executable=self._executable,
            arguments=("-NoLogo", "-NoProfile", "-NonInteractive", "-Command"),
            command_transport="argv",
        )

        async def execute(
            tool_call_id: str,
            params: PowerShellInput,
            abort_event: asyncio.Event | None,
            on_update: AgentToolUpdateCallback[dict[str, JsonValue]] | None,
        ) -> AgentToolResult[dict[str, JsonValue]]:
            del tool_call_id

            async def update(text: str) -> None:
                if on_update is not None:
                    on_update(_result(text))

            value = await execute_bash(
                params.command,
                cwd=cwd,
                config=config,
                operations=operations,
                timeout=params.timeout,
                abort_event=abort_event,
                on_update=update if on_update is not None else None,
            )
            if value.aborted:
                raise PowerShellToolError("PowerShell command aborted")
            if value.timed_out:
                raise PowerShellToolError("PowerShell command timed out")
            if value.exit_code not in (None, 0):
                raise PowerShellToolError(f"PowerShell command exited with code {value.exit_code}")
            return _result(
                value.output or "(no output)",
                {
                    "exitCode": value.exit_code,
                    "truncated": value.truncated,
                    "fullOutputPath": (
                        str(value.full_output_path) if value.full_output_path else None
                    ),
                },
            )

        return AgentTool(
            name="powershell",
            label="PowerShell",
            description="Execute a PowerShell command on Windows.",
            parameter_type=PowerShellInput,
            execute=execute,
            execution_mode="sequential",
        )


def _result(
    text: str, details: dict[str, JsonValue] | None = None
) -> AgentToolResult[dict[str, JsonValue]]:
    return AgentToolResult(
        content=(TextContent(text=text),),
        details={} if details is None else details,
    )


__all__ = ["PowerShellExtension", "PowerShellInput", "PowerShellToolError"]
