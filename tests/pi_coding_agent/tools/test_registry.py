from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
from pydantic import ValidationError

from pi_agent import AgentTool
from pi_ai import TextContent
from pi_coding_agent.tools import ALL_TOOL_NAMES, create_all_tools
from pi_coding_agent.tools.bash_resolver import BashConfig
from pi_coding_agent.tools.operations import DirectoryEntry, OutputSink, SearchMatch
from pi_coding_agent.tools.registry import EditInput


class RegistryFilesystemOperations:
    async def read_bytes(self, path: Path) -> bytes:
        return path.read_bytes()

    async def write_bytes(self, path: Path, data: bytes) -> None:
        path.write_bytes(data)

    async def replace(self, source: Path, destination: Path) -> None:
        source.replace(destination)

    async def make_parents(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)

    async def scan_directory(self, path: Path) -> tuple[DirectoryEntry, ...]:
        return (
            DirectoryEntry(name="dir", path=path / "dir", is_file=False, is_dir=True),
            DirectoryEntry(name="file.txt", path=path / "file.txt", is_file=True, is_dir=False),
        )


class RegistrySearchOperations:
    async def grep(
        self, pattern: str, root: Path, *, include_hidden: bool
    ) -> tuple[SearchMatch, ...]:
        del pattern, include_hidden
        return (SearchMatch(path=root / "file.txt", line=1, column=1, text="hit"),)

    async def find(self, pattern: str, root: Path, *, include_hidden: bool) -> tuple[Path, ...]:
        del pattern, include_hidden
        return (root / "file.txt",)


class RegistryProcessOperations:
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
        await stdout(b"command output")
        return 0


def _tools(tmp_path: Path) -> tuple[AgentTool[object, object], ...]:
    return create_all_tools(
        cwd=tmp_path,
        filesystem_operations=RegistryFilesystemOperations(),
        search_operations=RegistrySearchOperations(),
        process_operations=RegistryProcessOperations(),
        bash_config=BashConfig(
            executable="bash",
            arguments=("-c",),
            command_transport="argv",
        ),
    )


def test_registry_exports_canonical_order_and_object_rooted_schemas(tmp_path: Path) -> None:
    tools = _tools(tmp_path)

    assert tuple(tool.name for tool in tools) == ALL_TOOL_NAMES
    assert ALL_TOOL_NAMES == ("read", "bash", "edit", "write", "grep", "find", "ls")
    assert all(tool.parameters["type"] == "object" for tool in tools)
    edit_schema = json.dumps(tools[2].parameters, ensure_ascii=False)
    assert edit_schema.index('"oldText"') < edit_schema.index('"newText"')


def test_registry_parameter_validation_is_strict(tmp_path: Path) -> None:
    tools = {tool.name: tool for tool in _tools(tmp_path)}

    with pytest.raises(ValidationError):
        tools["read"].validate_arguments({"path": "file.txt", "offset": "1"})
    with pytest.raises(ValidationError):
        tools["write"].validate_arguments({"path": "file.txt"})
    with pytest.raises(ValidationError):
        tools["bash"].validate_arguments({"command": "x", "unknown": True})


def test_all_registered_tools_execute_through_agent_contract(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("old", encoding="utf-8")
    tools = {tool.name: tool for tool in _tools(tmp_path)}
    arguments = {
        "read": {"path": "source.txt"},
        "bash": {"command": "echo test"},
        "edit": {"path": "source.txt", "edits": [{"oldText": "old", "newText": "new"}]},
        "write": {"path": "written.txt", "content": "content"},
        "grep": {"pattern": "hit"},
        "find": {"pattern": "*.txt"},
        "ls": {},
    }

    async def scenario() -> dict[str, str]:
        outputs: dict[str, str] = {}
        for name in ALL_TOOL_NAMES:
            tool = tools[name]
            params = tool.validate_arguments(arguments[name])
            result = await tool.execute(f"call-{name}", params)
            content = result.content[0]
            assert isinstance(content, TextContent)
            outputs[name] = content.text
        return outputs

    outputs = asyncio.run(scenario())

    assert outputs["read"] == "old"
    assert outputs["bash"] == "command output"
    assert source.read_text(encoding="utf-8") == "new"
    assert (tmp_path / "written.txt").read_text(encoding="utf-8") == "content"
    assert outputs["grep"] == "file.txt:1:1:hit"
    assert outputs["find"] == "file.txt"
    assert outputs["ls"] == "dir/\nfile.txt"


def test_edit_prepare_arguments_accepts_json_string_and_legacy_shape(tmp_path: Path) -> None:
    edit_tool = _tools(tmp_path)[2]

    from_json = edit_tool.prepare_arguments(
        {"path": "file.txt", "edits": '[{"oldText":"a","newText":"b"}]'}
    )
    legacy = edit_tool.prepare_arguments({"path": "file.txt", "oldText": "a", "newText": "b"})

    validated_json = edit_tool.validate_arguments(from_json)
    validated_legacy = edit_tool.validate_arguments(legacy)
    assert isinstance(validated_json, EditInput)
    assert isinstance(validated_legacy, EditInput)
    assert validated_json.edits[0].old_text == "a"
    assert validated_legacy.edits[0].new_text == "b"


def test_create_readonly_tools_returns_read_grep_find_ls(tmp_path: Path) -> None:
    from pi_coding_agent.tools import create_readonly_tools

    tools = create_readonly_tools(cwd=tmp_path)
    assert tuple(tool.name for tool in tools) == ("read", "grep", "find", "ls")
