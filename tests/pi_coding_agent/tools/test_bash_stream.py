"""Bash binDir PATH prepend and throttled stream updates (P11.5-T14)."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from pathlib import Path

from pi_coding_agent.tools.bash import execute_bash
from pi_coding_agent.tools.bash_resolver import BashConfig
from pi_coding_agent.tools.operations import OutputSink
from pi_coding_agent.tools.registry import create_all_tools


class _CapturingProcessOperations:
    def __init__(self) -> None:
        self.environment: dict[str, str] | None = None
        self.updates: list[str] = []

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
        del cwd, timeout, abort_event, stderr
        self.environment = dict(environment) if environment is not None else None
        await stdout(b"chunk1\n")
        await stdout(b"chunk2\n")
        return 0


def _config() -> BashConfig:
    return BashConfig(executable="bash", arguments=("-c",), command_transport="argv")


class TestBinDirPath:
    def test_bin_dir_is_prepended_to_path_once(self) -> None:
        operations = _CapturingProcessOperations()
        bin_dir = Path("C:/pi-agent/bin")
        asyncio.run(
            execute_bash(
                "rg pattern",
                cwd=Path.cwd(),
                config=_config(),
                operations=operations,
                environment={"PATH": r"C:\Windows\system32"},
                bin_dir=bin_dir,
            )
        )
        assert operations.environment is not None
        assert operations.environment["PATH"].startswith(
            str(bin_dir) + ";"
        ) or operations.environment["PATH"].startswith(str(bin_dir) + ":")
        assert r"C:\Windows\system32" in operations.environment["PATH"]

    def test_existing_bin_dir_is_not_duplicated(self) -> None:
        operations = _CapturingProcessOperations()
        bin_dir = Path("C:/pi-agent/bin")
        asyncio.run(
            execute_bash(
                "rg pattern",
                cwd=Path.cwd(),
                config=_config(),
                operations=operations,
                environment={"PATH": str(bin_dir)},
                bin_dir=bin_dir,
            )
        )
        assert operations.environment is not None
        assert operations.environment["PATH"].count(str(bin_dir)) == 1

    def test_windows_pathect_case_is_normalized(self) -> None:
        operations = _CapturingProcessOperations()
        asyncio.run(
            execute_bash(
                "rg pattern",
                cwd=Path.cwd(),
                config=_config(),
                operations=operations,
                environment={"Path": r"C:\Windows"},
                bin_dir=Path("C:/pi-agent/bin"),
            )
        )
        assert operations.environment is not None
        assert "Path" in operations.environment
        assert "PATH" not in operations.environment


class TestThrottledUpdates:
    def test_rapid_chunks_coalesce_into_one_update(self) -> None:
        operations = _CapturingProcessOperations()

        async def scenario() -> None:
            async def on_update(content: str) -> None:
                operations.updates.append(content)

            await execute_bash(
                "echo hi",
                cwd=Path.cwd(),
                config=_config(),
                operations=operations,
                on_update=on_update,
            )

        asyncio.run(scenario())
        # Both chunks arrive back-to-back; throttling coalesces them into the
        # final flush plus at most one intermediate update.
        assert len(operations.updates) <= 2
        assert operations.updates[-1] == "chunk1\nchunk2\n"


def test_registry_bash_tool_wires_bin_dir(tmp_path: Path) -> None:
    operations = _CapturingProcessOperations()
    bin_dir = tmp_path / "bin"
    (bash_tool,) = create_all_tools(
        cwd=tmp_path,
        tool_names=("bash",),
        process_operations=operations,
        bash_config=_config(),
        bin_dir=bin_dir,
    )
    params = bash_tool.validate_arguments({"command": "rg pattern"})
    asyncio.run(bash_tool.execute("call-bash", params))
    assert operations.environment is not None
    assert str(bin_dir) in operations.environment["PATH"]
