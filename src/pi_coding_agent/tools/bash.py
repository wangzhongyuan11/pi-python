"""Cancellable Bash execution with bounded streaming output."""

from __future__ import annotations

import asyncio
import contextlib
import math
import os
import signal
import subprocess
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .bash_resolver import BashConfig, resolve_bash
from .operations import OutputSink, ProcessOperations
from .output import DEFAULT_MAX_BYTES, DEFAULT_MAX_LINES, OutputAccumulator

type UpdateSink = Callable[[str], Awaitable[None]]


class BashToolError(RuntimeError):
    pass


class ProcessAborted(RuntimeError):
    pass


class ProcessTimedOut(RuntimeError):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class BashResult:
    output: str
    exit_code: int | None
    aborted: bool
    timed_out: bool
    truncated: bool
    full_output_path: Path | None


class NativeProcessOperations:
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
        if abort_event is not None and abort_event.is_set():
            raise ProcessAborted
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        process = await asyncio.create_subprocess_exec(
            *argv,
            cwd=cwd,
            env=None if environment is None else dict(environment),
            stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=sys.platform != "win32",
            creationflags=creationflags,
        )
        if stdin is not None and process.stdin is not None:
            process.stdin.write(stdin)
            await process.stdin.drain()
            process.stdin.close()

        async def pump(reader: asyncio.StreamReader | None, sink: OutputSink) -> None:
            if reader is None:
                return
            while chunk := await reader.read(64 * 1024):
                await sink(chunk)

        pumps = [
            asyncio.create_task(pump(process.stdout, stdout)),
            asyncio.create_task(pump(process.stderr, stderr)),
        ]
        wait_task = asyncio.create_task(process.wait())
        abort_task = asyncio.create_task(abort_event.wait()) if abort_event is not None else None
        try:
            waiters: set[asyncio.Task[int] | asyncio.Task[bool]] = {wait_task}
            if abort_task is not None:
                waiters.add(abort_task)
            done, _ = await asyncio.wait(
                waiters,
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if wait_task not in done:
                await self._terminate_tree(process)
                await wait_task
                await asyncio.gather(*pumps)
                if abort_task is not None and abort_task in done:
                    raise ProcessAborted
                raise ProcessTimedOut
            await asyncio.gather(*pumps)
            return wait_task.result()
        except asyncio.CancelledError:
            await self._terminate_tree(process)
            await process.wait()
            await asyncio.gather(*pumps, return_exceptions=True)
            raise
        finally:
            if abort_task is not None:
                abort_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await abort_task

    async def _terminate_tree(self, process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        if sys.platform == "win32":
            taskkill = await asyncio.create_subprocess_exec(
                "taskkill",
                "/F",
                "/T",
                "/PID",
                str(process.pid),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            await taskkill.wait()
            if process.returncode is None:
                process.kill()
            return
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        except OSError:
            process.kill()


def _validate_timeout(timeout: float | None) -> None:
    if timeout is None:
        return
    if not math.isfinite(timeout) or timeout <= 0 or timeout * 1_000 > 2_147_483_647:
        raise BashToolError("Invalid timeout: must be a finite positive number of seconds")


async def execute_bash(
    command: str,
    *,
    cwd: Path,
    config: BashConfig | None = None,
    custom_shell_path: str | None = None,
    operations: ProcessOperations | None = None,
    environment: Mapping[str, str] | None = None,
    timeout: float | None = None,
    abort_event: asyncio.Event | None = None,
    on_update: UpdateSink | None = None,
    max_lines: int = DEFAULT_MAX_LINES,
    max_bytes: int = DEFAULT_MAX_BYTES,
    temp_dir: Path | None = None,
) -> BashResult:
    _validate_timeout(timeout)
    selected_config = (
        resolve_bash(custom_shell_path=custom_shell_path) if config is None else config
    )
    selected_operations = NativeProcessOperations() if operations is None else operations
    argv = [selected_config.executable, *selected_config.arguments]
    stdin = None
    if selected_config.command_transport == "stdin":
        stdin = command.encode("utf-8")
    else:
        argv.append(command)

    accumulator = OutputAccumulator(
        max_lines=max_lines,
        max_bytes=max_bytes,
        temp_dir=temp_dir,
    )
    accepting_output = True

    async def accept(data: bytes) -> None:
        if not accepting_output:
            return
        accumulator.append(data)
        if on_update is not None:
            await on_update(accumulator.snapshot().content)

    exit_code: int | None = None
    aborted = False
    timed_out = False
    try:
        exit_code = await selected_operations.run(
            argv,
            cwd=cwd,
            environment=environment,
            stdin=stdin,
            stdout=accept,
            stderr=accept,
            timeout=timeout,
            abort_event=abort_event,
        )
    except ProcessAborted:
        aborted = True
    except ProcessTimedOut:
        timed_out = True
    finally:
        accepting_output = False
        accumulator.finish()

    snapshot = accumulator.snapshot()
    output = snapshot.content
    if snapshot.truncated and snapshot.full_output_path is not None:
        start_line = snapshot.total_lines - snapshot.output_lines + 1
        output += (
            f"\n\n[Showing lines {start_line}-{snapshot.total_lines} of "
            f"{snapshot.total_lines}. Full output: {snapshot.full_output_path}]"
        )
    if on_update is not None:
        await on_update(output)
    return BashResult(
        output=output,
        exit_code=exit_code,
        aborted=aborted,
        timed_out=timed_out,
        truncated=snapshot.truncated,
        full_output_path=snapshot.full_output_path,
    )


__all__ = [
    "BashResult",
    "BashToolError",
    "NativeProcessOperations",
    "ProcessAborted",
    "ProcessTimedOut",
    "execute_bash",
]
