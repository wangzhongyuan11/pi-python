"""Production wiring for real search and listing operations (P11.5-T01)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from pi_ai import TextContent
from pi_coding_agent.tools.binaries import BinaryManager
from pi_coding_agent.tools.local_operations import (
    LocalFilesystemOperations,
    LocalSearchOperations,
)
from pi_coding_agent.tools.operations import OutputSink, SearchMatch
from pi_coding_agent.tools.registry import create_all_tools

RG = Path("C:/bin/rg.exe")
FD = Path("C:/bin/fd.exe")
ROOT = Path("Z:/root")


def _rg_json_line(path: str, line_number: int, column: int, text: str) -> bytes:
    payload = {
        "type": "match",
        "data": {
            "path": {"text": path},
            "line_number": line_number,
            "lines": {"text": f"{text}\n"},
            "submatches": [{"match": {"text": text}, "start": column, "end": column + len(text)}],
        },
    }
    return (json.dumps(payload) + "\n").encode("utf-8")


class FakeSearchProcessOperations:
    def __init__(self, stdout: bytes = b"", exit_code: int = 0) -> None:
        self.stdout = stdout
        self.exit_code = exit_code
        self.argv: tuple[str, ...] | None = None
        self.cwd: Path | None = None

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
        del environment, stdin, stderr, timeout, abort_event
        self.argv = tuple(argv)
        self.cwd = cwd
        if self.stdout:
            await stdout(self.stdout)
        return self.exit_code


def _offline_manager() -> BinaryManager:
    return BinaryManager(
        cache_dir=Path("Z:") / "unused" / "cache", offline=True, which=lambda name: None
    )


class TestFactoryBuildsRealOperations:
    def test_search_tools_are_constructible_without_injected_operations(
        self, tmp_path: Path
    ) -> None:
        tools = create_all_tools(
            cwd=tmp_path,
            tool_names=("read", "grep", "find", "ls"),
        )
        assert tuple(tool.name for tool in tools) == ("read", "grep", "find", "ls")

    def test_ls_executes_a_real_directory_scan(self, tmp_path: Path) -> None:
        (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")
        (tmp_path / "src").mkdir()
        tools = create_all_tools(cwd=tmp_path, tool_names=("ls",))
        (ls_tool,) = tools
        params = ls_tool.validate_arguments({"path": "."})
        result = asyncio.run(ls_tool.execute("call-1", params))
        content = result.content[0]
        assert isinstance(content, TextContent)
        assert "notes.txt" in content.text
        assert "src/" in content.text


class TestLocalFilesystemOperations:
    def test_scan_directory_reports_entries(self, tmp_path: Path) -> None:
        (tmp_path / "file.txt").write_text("x", encoding="utf-8")
        (tmp_path / "folder").mkdir()
        operations = LocalFilesystemOperations()
        entries = asyncio.run(operations.scan_directory(tmp_path))
        by_name = {entry.name: entry for entry in entries}
        assert {"file.txt", "folder"} <= set(by_name)
        assert by_name["file.txt"].is_file
        assert by_name["folder"].is_dir


class TestLocalSearchOperations:
    def test_grep_parses_rg_json_matches(self) -> None:
        process = FakeSearchProcessOperations(
            stdout=(
                _rg_json_line("src/a.py", 3, 6, "needle")
                + _rg_json_line("src/b.py", 11, 0, "needle here")
            )
        )
        operations = LocalSearchOperations(
            process_operations=process,
            binary_manager=_offline_manager(),
            binaries={"rg": RG, "fd": FD},
        )
        matches = asyncio.run(operations.grep("needle", ROOT, include_hidden=True))
        assert matches == (
            SearchMatch(path=ROOT / "src" / "a.py", line=3, column=6, text="needle"),
            SearchMatch(path=ROOT / "src" / "b.py", line=11, column=0, text="needle here"),
        )
        assert process.argv is not None
        assert process.argv[:1] == (str(RG),)
        assert process.argv[1:5] == ("--json", "--line-number", "--color=never", "--hidden")
        assert process.argv[-3:] == ("--", "needle", str(ROOT))

    def test_grep_omits_hidden_flag_when_not_including_hidden(self) -> None:
        process = FakeSearchProcessOperations()
        operations = LocalSearchOperations(
            process_operations=process,
            binary_manager=_offline_manager(),
            binaries={"rg": RG, "fd": FD},
        )
        asyncio.run(operations.grep("x", ROOT, include_hidden=False))
        assert process.argv is not None
        assert "--hidden" not in process.argv

    def test_grep_raises_search_tool_error_when_binary_unavailable(self) -> None:
        operations = LocalSearchOperations(
            process_operations=FakeSearchProcessOperations(),
            binary_manager=_offline_manager(),
        )
        with pytest.raises(Exception, match="rg") as excinfo:
            asyncio.run(operations.grep("x", ROOT, include_hidden=True))
        assert type(excinfo.value).__name__ == "SearchOperationError"

    def test_find_parses_fd_lines_into_paths(self) -> None:
        process = FakeSearchProcessOperations(stdout=b"src/a.py\nsrc/sub/b.py\n")
        operations = LocalSearchOperations(
            process_operations=process,
            binary_manager=_offline_manager(),
            binaries={"rg": RG, "fd": FD},
        )
        paths = asyncio.run(operations.find("*.py", ROOT, include_hidden=True))
        assert paths == (ROOT / "src" / "a.py", ROOT / "src" / "sub" / "b.py")
        assert process.argv is not None
        assert process.argv[:1] == (str(FD),)
        assert "--color=never" in process.argv
        assert process.argv[-3:] == ("--", "*.py", str(ROOT))

    def test_find_disables_git_requirement_outside_repositories(self, tmp_path: Path) -> None:
        process = FakeSearchProcessOperations(stdout=b"")
        operations = LocalSearchOperations(
            process_operations=process,
            binary_manager=_offline_manager(),
            binaries={"rg": RG, "fd": FD},
        )
        asyncio.run(operations.find("x", tmp_path, include_hidden=True))
        assert process.argv is not None
        assert "--no-require-git" in process.argv

    def test_find_keeps_git_aware_behavior_inside_repository(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        process = FakeSearchProcessOperations(stdout=b"")
        operations = LocalSearchOperations(
            process_operations=process,
            binary_manager=_offline_manager(),
            binaries={"rg": RG, "fd": FD},
        )
        asyncio.run(operations.find("x", tmp_path, include_hidden=True))
        assert process.argv is not None
        assert "--no-require-git" not in process.argv
