"""Operating-system ports used by coding tools."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

type OutputSink = Callable[[bytes], Awaitable[None]]


@dataclass(frozen=True, slots=True, kw_only=True)
class DirectoryEntry:
    name: str
    path: Path
    is_file: bool
    is_dir: bool
    is_symlink: bool = False
    size: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class SearchMatch:
    path: Path
    line: int
    column: int
    text: str


class FilesystemOperations(Protocol):
    async def read_bytes(self, path: Path) -> bytes: ...

    async def write_bytes(self, path: Path, data: bytes) -> None: ...

    async def replace(self, source: Path, destination: Path) -> None: ...

    async def make_parents(self, path: Path) -> None: ...

    async def scan_directory(self, path: Path) -> tuple[DirectoryEntry, ...]: ...


class ProcessOperations(Protocol):
    async def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        environment: Mapping[str, str] | None,
        stdout: OutputSink,
        stderr: OutputSink,
        timeout: float | None,
        abort_event: asyncio.Event | None,
    ) -> int: ...


class SearchOperations(Protocol):
    async def grep(
        self,
        pattern: str,
        root: Path,
        *,
        include_hidden: bool,
    ) -> tuple[SearchMatch, ...]: ...

    async def find(
        self,
        pattern: str,
        root: Path,
        *,
        include_hidden: bool,
    ) -> tuple[Path, ...]: ...


__all__ = [
    "DirectoryEntry",
    "FilesystemOperations",
    "OutputSink",
    "ProcessOperations",
    "SearchMatch",
    "SearchOperations",
]
