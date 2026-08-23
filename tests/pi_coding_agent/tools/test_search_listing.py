from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from pi_coding_agent.tools.listing import ListToolError, list_directory
from pi_coding_agent.tools.operations import DirectoryEntry, SearchMatch
from pi_coding_agent.tools.search import SearchToolError, find_files, grep_files


class FakeSearchOperations:
    def __init__(
        self,
        *,
        grep_matches: tuple[SearchMatch, ...] = (),
        find_paths: tuple[Path, ...] = (),
        error: OSError | None = None,
    ) -> None:
        self.grep_matches = grep_matches
        self.find_paths = find_paths
        self.error = error
        self.include_hidden: bool | None = None
        self.calls = 0

    async def grep(
        self, pattern: str, root: Path, *, include_hidden: bool
    ) -> tuple[SearchMatch, ...]:
        del pattern, root
        self.calls += 1
        self.include_hidden = include_hidden
        if self.error is not None:
            raise self.error
        return self.grep_matches

    async def find(self, pattern: str, root: Path, *, include_hidden: bool) -> tuple[Path, ...]:
        del pattern, root
        self.calls += 1
        self.include_hidden = include_hidden
        if self.error is not None:
            raise self.error
        return self.find_paths


class FakeFilesystemOperations:
    def __init__(
        self,
        *,
        directory_entries: tuple[DirectoryEntry, ...] = (),
        error: OSError | None = None,
    ) -> None:
        self.directory_entries = directory_entries
        self.error = error

    async def read_bytes(self, path: Path) -> bytes:
        raise NotImplementedError(path)

    async def write_bytes(self, path: Path, data: bytes) -> None:
        raise NotImplementedError(path, data)

    async def replace(self, source: Path, destination: Path) -> None:
        raise NotImplementedError(source, destination)

    async def make_parents(self, path: Path) -> None:
        raise NotImplementedError(path)

    async def scan_directory(self, path: Path) -> tuple[DirectoryEntry, ...]:
        del path
        if self.error is not None:
            raise self.error
        return self.directory_entries


def test_grep_sorts_matches_and_truncates_long_lines(tmp_path: Path) -> None:
    root = tmp_path / "项目"
    matches = (
        SearchMatch(path=root / "z.py", line=9, column=2, text="z"),
        SearchMatch(path=root / "A.py", line=2, column=1, text="x" * 600),
        SearchMatch(path=root / "A.py", line=1, column=3, text="中文"),
    )
    operations = FakeSearchOperations(grep_matches=matches)

    result = asyncio.run(grep_files("pattern", root, cwd=tmp_path, operations=operations))

    assert [match.line for match in result.matches] == [1, 2, 9]
    assert result.text.splitlines()[0] == "A.py:1:3:中文"
    assert result.text.splitlines()[1].endswith("... [truncated]")
    assert result.lines_truncated
    assert operations.include_hidden is True


def test_grep_limit_is_explicit_and_stable(tmp_path: Path) -> None:
    operations = FakeSearchOperations(
        grep_matches=tuple(
            SearchMatch(path=tmp_path / f"{index}.txt", line=1, column=1, text="hit")
            for index in range(3)
        )
    )

    result = asyncio.run(grep_files("hit", ".", cwd=tmp_path, operations=operations, limit=2))

    assert len(result.matches) == 2
    assert result.limit_reached == 2
    assert "2 matches limit reached" in result.text


def test_find_relativizes_and_sorts_paths(tmp_path: Path) -> None:
    root = tmp_path / "root"
    operations = FakeSearchOperations(
        find_paths=(root / "z.txt", root / "目录" / "a.txt", root / "A.txt")
    )

    result = asyncio.run(find_files("*.txt", root, cwd=tmp_path, operations=operations))

    assert result.paths == ("A.txt", "z.txt", "目录/a.txt")
    assert result.text == "A.txt\nz.txt\n目录/a.txt"


def test_ls_includes_hidden_entries_and_marks_directories(tmp_path: Path) -> None:
    root = tmp_path / "root"
    operations = FakeFilesystemOperations(
        directory_entries=(
            DirectoryEntry(name="z.txt", path=root / "z.txt", is_file=True, is_dir=False),
            DirectoryEntry(name=".hidden", path=root / ".hidden", is_file=True, is_dir=False),
            DirectoryEntry(name="目录", path=root / "目录", is_file=False, is_dir=True),
            DirectoryEntry(name="A.txt", path=root / "A.txt", is_file=True, is_dir=False),
        )
    )

    result = asyncio.run(list_directory(root, cwd=tmp_path, operations=operations))

    assert result.entries == (".hidden", "A.txt", "z.txt", "目录/")
    assert result.text == ".hidden\nA.txt\nz.txt\n目录/"


def test_search_and_listing_validate_limits_and_translate_operation_errors(tmp_path: Path) -> None:
    search = FakeSearchOperations(error=OSError("search failed"))
    filesystem = FakeFilesystemOperations(error=OSError("listing failed"))

    with pytest.raises(SearchToolError, match="search failed"):
        asyncio.run(grep_files("x", ".", cwd=tmp_path, operations=search))
    with pytest.raises(ListToolError, match="listing failed"):
        asyncio.run(list_directory(".", cwd=tmp_path, operations=filesystem))
    with pytest.raises(SearchToolError, match="positive integer"):
        asyncio.run(find_files("*", ".", cwd=tmp_path, operations=search, limit=0))


def test_pre_aborted_search_does_not_call_operations(tmp_path: Path) -> None:
    abort_event = asyncio.Event()
    abort_event.set()
    operations = FakeSearchOperations()

    with pytest.raises(SearchToolError, match="aborted"):
        asyncio.run(
            find_files(
                "*",
                ".",
                cwd=tmp_path,
                operations=operations,
                abort_event=abort_event,
            )
        )

    assert operations.calls == 0
