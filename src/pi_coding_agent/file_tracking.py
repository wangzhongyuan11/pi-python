"""Reduce branch Tool Calls into deterministic file operation sets."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .session.models import MessageEntry, SessionEntry

_FILE_TOOLS = {"read": "read", "write": "written", "edit": "edited"}


@dataclass(frozen=True, slots=True)
class FileOperations:
    read: frozenset[str]
    written: frozenset[str]
    edited: frozenset[str]


@dataclass(frozen=True, slots=True)
class FileOperationLists:
    read_files: tuple[str, ...]
    modified_files: tuple[str, ...]


def track_file_operations(entries: Sequence[SessionEntry]) -> FileOperations:
    read: set[str] = set()
    written: set[str] = set()
    edited: set[str] = set()
    for entry in entries:
        if not isinstance(entry, MessageEntry):
            continue
        message = entry.message
        if message.get("role") != "assistant":
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "toolCall":
                continue
            name = block.get("name")
            target = _FILE_TOOLS.get(name) if isinstance(name, str) else None
            if target is None:
                continue
            arguments = block.get("arguments")
            path = arguments.get("path") if isinstance(arguments, dict) else None
            if not isinstance(path, str) or not path:
                continue
            if target == "read":
                read.add(path)
            elif target == "written":
                written.add(path)
            else:
                edited.add(path)
    return FileOperations(
        read=frozenset(read), written=frozenset(written), edited=frozenset(edited)
    )


def compute_file_lists(file_ops: FileOperations) -> FileOperationLists:
    modified = file_ops.edited | file_ops.written
    return FileOperationLists(
        read_files=tuple(sorted(file_ops.read - modified)),
        modified_files=tuple(sorted(modified)),
    )


__all__ = ["FileOperationLists", "FileOperations", "compute_file_lists", "track_file_operations"]
