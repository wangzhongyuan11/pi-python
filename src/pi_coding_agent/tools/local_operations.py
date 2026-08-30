"""Real OS-backed implementations of the coding tool operation ports."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol, cast

from .binaries import ToolName
from .operations import DirectoryEntry, ProcessOperations, SearchMatch


class SearchOperationError(RuntimeError):
    """A search binary could not be resolved or failed to run."""


class BinaryResolver(Protocol):
    async def resolve(self, tool: ToolName) -> Path: ...


async def _collect_stdout(
    process_operations: ProcessOperations,
    argv: Sequence[str],
    *,
    cwd: Path,
) -> tuple[bytes, int]:
    chunks: list[bytes] = []

    async def stdout(data: bytes) -> None:
        chunks.append(data)

    async def stderr(data: bytes) -> None:
        return None

    exit_code = await process_operations.run(
        argv,
        cwd=cwd,
        environment=None,
        stdin=None,
        stdout=stdout,
        stderr=stderr,
        timeout=None,
        abort_event=None,
    )
    return b"".join(chunks), exit_code


def _rg_matches(output: bytes, root: Path) -> tuple[SearchMatch, ...]:
    matches: list[SearchMatch] = []
    for raw_line in output.decode("utf-8", errors="replace").splitlines():
        if not raw_line:
            continue
        try:
            event_object: object = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event_object, dict):
            continue
        event = cast("dict[str, object]", event_object)
        if event.get("type") != "match":
            continue
        data_object = event.get("data")
        if not isinstance(data_object, dict):
            continue
        data = cast("dict[str, object]", data_object)
        path_field = _string_field(data, "path")
        line_number = data.get("line_number")
        lines_field = _string_field(data, "lines")
        submatches_object = data.get("submatches")
        if (
            path_field is None
            or not isinstance(line_number, int)
            or isinstance(line_number, bool)
            or lines_field is None
            or not isinstance(submatches_object, list)
            or not submatches_object
        ):
            continue
        submatches = cast("list[object]", submatches_object)
        first_object = submatches[0]
        if not isinstance(first_object, dict):
            continue
        first = cast("dict[str, object]", first_object)
        match_field = _string_field(first, "match")
        column = first.get("start")
        if match_field is None or not isinstance(column, int) or isinstance(column, bool):
            continue
        matches.append(
            SearchMatch(
                path=root / path_field,
                line=line_number,
                column=column,
                text=lines_field.rstrip("\r\n"),
            )
        )
    return tuple(matches)


def _string_field(payload: dict[str, object], key: str) -> str | None:
    field_object = payload.get(key)
    if not isinstance(field_object, dict):
        return None
    text = cast("dict[str, object]", field_object).get("text")
    return text if isinstance(text, str) else None


def _inside_git_repo(start: Path) -> bool:
    current = start
    while True:
        try:
            if (current / ".git").exists():
                return True
        except OSError:
            return False
        parent = current.parent
        if parent == current:
            return False
        current = parent


class LocalSearchOperations:
    """Runs pinned or system ripgrep/fd binaries through the process port."""

    __slots__ = ("_binaries", "_binary_manager", "_process_operations")

    def __init__(
        self,
        *,
        process_operations: ProcessOperations,
        binary_manager: BinaryResolver,
        binaries: Mapping[str, Path] | None = None,
    ) -> None:
        self._process_operations = process_operations
        self._binary_manager = binary_manager
        self._binaries: dict[str, Path] = dict(binaries) if binaries else {}

    async def _resolve(self, tool: ToolName) -> Path:
        override = self._binaries.get(tool)
        if override is not None:
            return override
        try:
            return await self._binary_manager.resolve(tool)
        except Exception as error:
            raise SearchOperationError(f"{tool} is unavailable: {error}") from None

    async def grep(
        self,
        pattern: str,
        root: Path,
        *,
        include_hidden: bool,
    ) -> tuple[SearchMatch, ...]:
        rg = await self._resolve("rg")
        argv = [str(rg), "--json", "--line-number", "--color=never"]
        if include_hidden:
            argv.append("--hidden")
        argv += ["--", pattern, str(root)]
        try:
            output, _exit_code = await _collect_stdout(self._process_operations, argv, cwd=root)
        except (OSError, RuntimeError) as error:
            raise SearchOperationError(f"rg failed: {error}") from None
        return _rg_matches(output, root)

    async def find(
        self,
        pattern: str,
        root: Path,
        *,
        include_hidden: bool,
    ) -> tuple[Path, ...]:
        fd = await self._resolve("fd")
        argv = [str(fd), "--color=never"]
        if include_hidden:
            argv.append("--hidden")
        if not _inside_git_repo(root):
            argv.append("--no-require-git")
        argv += ["--", pattern, str(root)]
        try:
            output, _exit_code = await _collect_stdout(self._process_operations, argv, cwd=root)
        except (OSError, RuntimeError) as error:
            raise SearchOperationError(f"fd failed: {error}") from None
        return tuple(
            root / line for line in output.decode("utf-8", errors="replace").splitlines() if line
        )


class LocalFilesystemOperations:
    """Threaded real-filesystem implementation of the listing port."""

    async def read_bytes(self, path: Path) -> bytes:
        return await asyncio.to_thread(path.read_bytes)

    async def write_bytes(self, path: Path, data: bytes) -> None:
        await asyncio.to_thread(path.write_bytes, data)

    async def replace(self, source: Path, destination: Path) -> None:
        await asyncio.to_thread(os.replace, source, destination)

    async def make_parents(self, path: Path) -> None:
        await asyncio.to_thread(path.mkdir, True, exist_ok=True)

    async def scan_directory(self, path: Path) -> tuple[DirectoryEntry, ...]:
        def _scan() -> tuple[DirectoryEntry, ...]:
            entries: list[DirectoryEntry] = []
            with os.scandir(path) as scan:
                for item in scan:
                    entries.append(
                        DirectoryEntry(
                            name=item.name,
                            path=Path(item.path),
                            is_file=item.is_file(follow_symlinks=False),
                            is_dir=item.is_dir(follow_symlinks=False),
                            is_symlink=item.is_symlink(),
                        )
                    )
            return tuple(entries)

        return await asyncio.to_thread(_scan)


__all__ = [
    "BinaryResolver",
    "LocalFilesystemOperations",
    "LocalSearchOperations",
    "SearchOperationError",
]
