from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from pi_coding_agent.tools.bash import (
    BashToolError,
    ProcessAborted,
    ProcessTimedOut,
    execute_bash,
)
from pi_coding_agent.tools.bash_resolver import BashConfig
from pi_coding_agent.tools.operations import OutputSink


class FakeProcessOperations:
    def __init__(
        self,
        *,
        chunks: Sequence[tuple[str, bytes]] = (),
        exit_code: int = 0,
        error: Exception | None = None,
    ) -> None:
        self.chunks = chunks
        self.exit_code = exit_code
        self.error = error
        self.argv: tuple[str, ...] | None = None
        self.stdin: bytes | None = None
        self.environment: Mapping[str, str] | None = None

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
        del cwd, timeout, abort_event
        self.argv = tuple(argv)
        self.stdin = stdin
        self.environment = environment
        for stream, chunk in self.chunks:
            await (stdout if stream == "stdout" else stderr)(chunk)
        if self.error is not None:
            raise self.error
        return self.exit_code


def _config(*, stdin: bool = False) -> BashConfig:
    return BashConfig(
        executable="bash",
        arguments=("-s",) if stdin else ("-c",),
        command_transport="stdin" if stdin else "argv",
    )


def test_streams_combined_output_and_reports_exit_code(tmp_path: Path) -> None:
    operations = FakeProcessOperations(
        chunks=(("stdout", b"hello\n"), ("stderr", "错误\n".encode())),
        exit_code=7,
    )
    updates: list[str] = []

    async def on_update(text: str) -> None:
        updates.append(text)

    result = asyncio.run(
        execute_bash(
            "printf test",
            cwd=tmp_path,
            config=_config(),
            operations=operations,
            on_update=on_update,
        )
    )

    assert operations.argv == ("bash", "-c", "printf test")
    assert operations.stdin is None
    assert result.output == "hello\n错误\n"
    assert result.exit_code == 7
    assert not result.aborted
    assert updates[-1] == result.output


def test_legacy_wsl_transport_sends_command_on_stdin(tmp_path: Path) -> None:
    operations = FakeProcessOperations()

    asyncio.run(
        execute_bash(
            "echo test",
            cwd=tmp_path,
            config=_config(stdin=True),
            operations=operations,
            environment={"SAFE": "value"},
        )
    )

    assert operations.argv == ("bash", "-s")
    assert operations.stdin == b"echo test"
    assert operations.environment == {"SAFE": "value"}


def test_tail_truncation_saves_complete_output(tmp_path: Path) -> None:
    operations = FakeProcessOperations(chunks=(("stdout", b"one\ntwo\nthree\n"),))

    result = asyncio.run(
        execute_bash(
            "command",
            cwd=tmp_path,
            config=_config(),
            operations=operations,
            max_lines=2,
            max_bytes=100,
            temp_dir=tmp_path,
        )
    )

    assert result.truncated
    assert result.output.startswith("two\nthree")
    assert result.full_output_path is not None
    assert result.full_output_path.read_bytes() == b"one\ntwo\nthree\n"


@pytest.mark.parametrize(
    ("error", "aborted", "timed_out"),
    [(ProcessAborted(), True, False), (ProcessTimedOut(), False, True)],
)
def test_abort_and_timeout_are_typed_terminal_results(
    tmp_path: Path, error: Exception, aborted: bool, timed_out: bool
) -> None:
    operations = FakeProcessOperations(chunks=(("stdout", b"partial"),), error=error)

    result = asyncio.run(
        execute_bash(
            "command",
            cwd=tmp_path,
            config=_config(),
            operations=operations,
            timeout=1,
        )
    )

    assert result.output == "partial"
    assert result.exit_code is None
    assert result.aborted is aborted
    assert result.timed_out is timed_out


def test_late_output_after_abort_is_ignored(tmp_path: Path) -> None:
    class LateOperations(FakeProcessOperations):
        late_task: asyncio.Task[None] | None = None

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
            del argv, cwd, environment, stdin, stderr, timeout, abort_event
            await stdout(b"before")

            async def emit_late() -> None:
                await asyncio.sleep(0)
                await stdout(b"-late")

            self.late_task = asyncio.create_task(emit_late())
            raise ProcessAborted

    async def scenario() -> tuple[str, str]:
        operations = LateOperations()
        updates: list[str] = []

        async def on_update(text: str) -> None:
            updates.append(text)

        result = await execute_bash(
            "command",
            cwd=tmp_path,
            config=_config(),
            operations=operations,
            on_update=on_update,
        )
        assert operations.late_task is not None
        await operations.late_task
        return result.output, updates[-1]

    assert asyncio.run(scenario()) == ("before", "before")


@pytest.mark.parametrize("timeout", [0, -1, float("inf")])
def test_invalid_timeout_is_rejected(tmp_path: Path, timeout: float) -> None:
    with pytest.raises(BashToolError, match="Invalid timeout"):
        asyncio.run(
            execute_bash(
                "command",
                cwd=tmp_path,
                config=_config(),
                operations=FakeProcessOperations(),
                timeout=timeout,
            )
        )
