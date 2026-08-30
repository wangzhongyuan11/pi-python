"""All-or-nothing exact text edits for coding-agent tools."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .edit_diff import generate_diff_string, generate_unified_patch
from .mutation_queue import FileMutationQueue, default_mutation_queue
from .paths import resolve_tool_path
from .write import WriteToolError, write_resolved_bytes


class EditToolError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class Edit:
    old_text: str
    new_text: str


@dataclass(frozen=True, slots=True, kw_only=True)
class EditResult:
    path: Path
    replacements: int
    diff: str = ""
    patch: str = ""
    first_changed_line: int | None = None


@dataclass(frozen=True, slots=True)
class _Match:
    edit_index: int
    start: int
    end: int
    replacement: str


def _line_ending(content: str) -> str:
    first_lf = content.find("\n")
    if first_lf > 0 and content[first_lf - 1] == "\r":
        return "\r\n"
    return "\n"


def _normalize_newlines(content: str) -> str:
    return content.replace("\r\n", "\n").replace("\r", "\n")


def _prepare_edits(content: str, edits: Sequence[Edit], path: Path) -> str:
    if not edits:
        raise EditToolError("Edit operation requires at least one replacement")

    normalized_edits = [
        Edit(
            old_text=_normalize_newlines(edit.old_text),
            new_text=_normalize_newlines(edit.new_text),
        )
        for edit in edits
    ]
    matches: list[_Match] = []
    for index, edit in enumerate(normalized_edits):
        if not edit.old_text:
            raise EditToolError(f"edits[{index}].old_text must not be empty in {path}")
        occurrences = content.count(edit.old_text)
        if occurrences == 0:
            raise EditToolError(f"Could not find edits[{index}] in {path}")
        if occurrences > 1:
            raise EditToolError(
                f"Found {occurrences} occurrences of edits[{index}] in {path}; "
                "old_text must be unique"
            )
        start = content.index(edit.old_text)
        matches.append(
            _Match(
                edit_index=index,
                start=start,
                end=start + len(edit.old_text),
                replacement=edit.new_text,
            )
        )

    matches.sort(key=lambda match: match.start)
    for previous, current in zip(matches, matches[1:], strict=False):
        if previous.end > current.start:
            raise EditToolError(
                f"edits[{previous.edit_index}] and edits[{current.edit_index}] overlap in {path}"
            )

    result = content
    for match in reversed(matches):
        result = result[: match.start] + match.replacement + result[match.end :]
    if result == content:
        raise EditToolError(f"No changes made to {path}")
    return result


async def edit_file(
    path: str | Path,
    edits: Sequence[Edit],
    *,
    cwd: Path,
    abort_event: asyncio.Event | None = None,
    mutation_queue: FileMutationQueue | None = None,
) -> EditResult:
    if abort_event is not None and abort_event.is_set():
        raise EditToolError("Edit operation aborted")
    resolved = resolve_tool_path(path, cwd=cwd)

    async def edit_resolved() -> EditResult:
        if abort_event is not None and abort_event.is_set():
            raise EditToolError("Edit operation aborted")
        try:
            raw = await asyncio.to_thread(resolved.read_bytes)
        except OSError as error:
            reason = error.strerror or type(error).__name__
            raise EditToolError(f"Could not edit {resolved}: {reason}") from None
        if abort_event is not None and abort_event.is_set():
            raise EditToolError("Edit operation aborted")

        decoded = raw.decode("utf-8", errors="replace")
        bom = "\ufeff" if decoded.startswith("\ufeff") else ""
        content = decoded[len(bom) :]
        ending = _line_ending(content)
        normalized = _normalize_newlines(content)
        edited = _prepare_edits(normalized, edits, resolved)
        restored = edited.replace("\n", "\r\n") if ending == "\r\n" else edited
        if abort_event is not None and abort_event.is_set():
            raise EditToolError("Edit operation aborted")
        try:
            await write_resolved_bytes(resolved, (bom + restored).encode("utf-8"), abort_event)
        except WriteToolError as error:
            raise EditToolError(str(error)) from None
        diff = generate_diff_string(normalized, edited)
        patch = generate_unified_patch(resolved.as_posix(), normalized, edited)
        return EditResult(
            path=resolved,
            replacements=len(edits),
            diff=diff.diff,
            patch=patch,
            first_changed_line=diff.first_changed_line,
        )

    queue = default_mutation_queue() if mutation_queue is None else mutation_queue
    return await queue.run(resolved, cwd=cwd, operation=edit_resolved)


__all__ = ["Edit", "EditResult", "EditToolError", "edit_file"]
