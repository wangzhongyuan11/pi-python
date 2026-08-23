"""Canonical AgentTool registry for the coding product."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from pi_agent import AgentTool, AgentToolResult, AgentToolUpdateCallback
from pi_ai import JsonValue, TextContent

from .bash import BashToolError, execute_bash
from .bash_resolver import BashConfig
from .edit import Edit, edit_file
from .listing import list_directory
from .mutation_queue import FileMutationQueue
from .operations import FilesystemOperations, ProcessOperations, SearchOperations
from .read import read_file
from .search import find_files, grep_files
from .write import write_file

ALL_TOOL_NAMES = ("read", "bash", "edit", "write", "grep", "find", "ls")


class _InputModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        strict=True,
    )


class ReadInput(_InputModel):
    path: str
    offset: int | None = Field(default=None, gt=0)
    limit: int | None = Field(default=None, gt=0)


class BashInput(_InputModel):
    command: str
    timeout: float | None = None


class EditReplacementInput(_InputModel):
    old_text: str
    new_text: str


class EditInput(_InputModel):
    path: str
    edits: list[EditReplacementInput] = Field(min_length=1)


class WriteInput(_InputModel):
    path: str
    content: str


class GrepInput(_InputModel):
    pattern: str
    path: str | None = None
    limit: int | None = Field(default=None, gt=0)


class FindInput(_InputModel):
    pattern: str
    path: str | None = None
    limit: int | None = Field(default=None, gt=0)


class ListInput(_InputModel):
    path: str | None = None
    limit: int | None = Field(default=None, gt=0)


type ToolDetails = dict[str, JsonValue]


def _result(text: str, details: ToolDetails | None = None) -> AgentToolResult[ToolDetails]:
    return AgentToolResult(
        content=(TextContent(text=text),),
        details={} if details is None else details,
    )


def _prepare_edit_arguments(raw: object) -> object:
    if not isinstance(raw, Mapping):
        return raw
    mapping = cast("Mapping[object, object]", raw)
    prepared: dict[str, object] = {
        key: value for key, value in mapping.items() if isinstance(key, str)
    }
    encoded_edits = prepared.get("edits")
    if isinstance(encoded_edits, str):
        try:
            parsed = cast("object", json.loads(encoded_edits))
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            prepared["edits"] = parsed
    old_text = prepared.pop("oldText", None)
    new_text = prepared.pop("newText", None)
    if isinstance(old_text, str) and isinstance(new_text, str):
        edits = prepared.get("edits")
        combined: list[object] = (
            list(cast("list[object] | tuple[object, ...]", edits))
            if isinstance(edits, list | tuple)
            else []
        )
        combined.append({"oldText": old_text, "newText": new_text})
        prepared["edits"] = combined
    return prepared


def create_all_tools(
    *,
    cwd: Path,
    filesystem_operations: FilesystemOperations,
    search_operations: SearchOperations,
    process_operations: ProcessOperations | None = None,
    bash_config: BashConfig | None = None,
    mutation_queue: FileMutationQueue | None = None,
) -> tuple[AgentTool[Any, Any], ...]:
    queue = FileMutationQueue() if mutation_queue is None else mutation_queue

    async def execute_read(
        tool_call_id: str,
        params: ReadInput,
        abort_event: asyncio.Event | None,
        on_update: AgentToolUpdateCallback[ToolDetails] | None,
    ) -> AgentToolResult[ToolDetails]:
        del tool_call_id, on_update
        value = await read_file(
            params.path,
            cwd=cwd,
            offset=params.offset,
            limit=params.limit,
            abort_event=abort_event,
        )
        return _result(
            value.text,
            {
                "path": str(value.path),
                "truncated": value.truncated,
                "nextOffset": value.next_offset,
            },
        )

    async def execute_bash_tool(
        tool_call_id: str,
        params: BashInput,
        abort_event: asyncio.Event | None,
        on_update: AgentToolUpdateCallback[ToolDetails] | None,
    ) -> AgentToolResult[ToolDetails]:
        del tool_call_id

        async def update(text: str) -> None:
            if on_update is not None:
                on_update(_result(text))

        value = await execute_bash(
            params.command,
            cwd=cwd,
            config=bash_config,
            operations=process_operations,
            timeout=params.timeout,
            abort_event=abort_event,
            on_update=update if on_update is not None else None,
        )
        if value.aborted:
            raise BashToolError(f"{value.output}\n\nCommand aborted".strip())
        if value.timed_out:
            raise BashToolError(
                f"{value.output}\n\nCommand timed out after {params.timeout} seconds".strip()
            )
        if value.exit_code not in (None, 0):
            raise BashToolError(
                f"{value.output}\n\nCommand exited with code {value.exit_code}".strip()
            )
        return _result(
            value.output or "(no output)",
            {
                "exitCode": value.exit_code,
                "truncated": value.truncated,
                "fullOutputPath": (
                    str(value.full_output_path) if value.full_output_path is not None else None
                ),
            },
        )

    async def execute_edit(
        tool_call_id: str,
        params: EditInput,
        abort_event: asyncio.Event | None,
        on_update: AgentToolUpdateCallback[ToolDetails] | None,
    ) -> AgentToolResult[ToolDetails]:
        del tool_call_id, on_update
        value = await edit_file(
            params.path,
            [Edit(old_text=item.old_text, new_text=item.new_text) for item in params.edits],
            cwd=cwd,
            abort_event=abort_event,
            mutation_queue=queue,
        )
        return _result(
            f"Successfully replaced {value.replacements} block(s) in {params.path}.",
            {"path": str(value.path), "replacements": value.replacements},
        )

    async def execute_write(
        tool_call_id: str,
        params: WriteInput,
        abort_event: asyncio.Event | None,
        on_update: AgentToolUpdateCallback[ToolDetails] | None,
    ) -> AgentToolResult[ToolDetails]:
        del tool_call_id, on_update
        value = await write_file(
            params.path,
            params.content,
            cwd=cwd,
            abort_event=abort_event,
            mutation_queue=queue,
        )
        return _result(
            f"Successfully wrote {params.path}.",
            {"path": str(value.path), "bytesWritten": value.bytes_written},
        )

    async def execute_grep(
        tool_call_id: str,
        params: GrepInput,
        abort_event: asyncio.Event | None,
        on_update: AgentToolUpdateCallback[ToolDetails] | None,
    ) -> AgentToolResult[ToolDetails]:
        del tool_call_id, on_update
        value = await grep_files(
            params.pattern,
            params.path or ".",
            cwd=cwd,
            operations=search_operations,
            limit=params.limit,
            abort_event=abort_event,
        )
        return _result(
            value.text,
            {
                "limitReached": value.limit_reached,
                "linesTruncated": value.lines_truncated,
                "bytesTruncated": value.bytes_truncated,
            },
        )

    async def execute_find(
        tool_call_id: str,
        params: FindInput,
        abort_event: asyncio.Event | None,
        on_update: AgentToolUpdateCallback[ToolDetails] | None,
    ) -> AgentToolResult[ToolDetails]:
        del tool_call_id, on_update
        value = await find_files(
            params.pattern,
            params.path or ".",
            cwd=cwd,
            operations=search_operations,
            limit=params.limit,
            abort_event=abort_event,
        )
        return _result(
            value.text,
            {
                "limitReached": value.limit_reached,
                "bytesTruncated": value.bytes_truncated,
            },
        )

    async def execute_list(
        tool_call_id: str,
        params: ListInput,
        abort_event: asyncio.Event | None,
        on_update: AgentToolUpdateCallback[ToolDetails] | None,
    ) -> AgentToolResult[ToolDetails]:
        del tool_call_id, on_update
        value = await list_directory(
            params.path or ".",
            cwd=cwd,
            operations=filesystem_operations,
            limit=params.limit,
            abort_event=abort_event,
        )
        return _result(
            value.text,
            {
                "limitReached": value.limit_reached,
                "bytesTruncated": value.bytes_truncated,
            },
        )

    return (
        AgentTool(
            name="read",
            label="read",
            description="Read a text file with optional line offset and limit.",
            parameter_type=ReadInput,
            execute=execute_read,
        ),
        AgentTool(
            name="bash",
            label="bash",
            description="Execute a Bash command and return combined stdout and stderr.",
            parameter_type=BashInput,
            execute=execute_bash_tool,
        ),
        AgentTool(
            name="edit",
            label="edit",
            description="Apply unique, non-overlapping exact text replacements to one file.",
            parameter_type=EditInput,
            execute=execute_edit,
            prepare_arguments=_prepare_edit_arguments,
        ),
        AgentTool(
            name="write",
            label="write",
            description="Atomically write complete UTF-8 content to a file.",
            parameter_type=WriteInput,
            execute=execute_write,
        ),
        AgentTool(
            name="grep",
            label="grep",
            description="Search file contents and return matching lines in stable order.",
            parameter_type=GrepInput,
            execute=execute_grep,
        ),
        AgentTool(
            name="find",
            label="find",
            description="Find paths matching a pattern and return stable relative paths.",
            parameter_type=FindInput,
            execute=execute_find,
        ),
        AgentTool(
            name="ls",
            label="ls",
            description="List directory entries in stable case-insensitive order.",
            parameter_type=ListInput,
            execute=execute_list,
        ),
    )


__all__ = [
    "ALL_TOOL_NAMES",
    "BashInput",
    "EditInput",
    "EditReplacementInput",
    "FindInput",
    "GrepInput",
    "ListInput",
    "ReadInput",
    "WriteInput",
    "create_all_tools",
]
