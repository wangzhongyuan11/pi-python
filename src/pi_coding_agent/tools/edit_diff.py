"""Display diffs and unified patches for edit results (port of edit-diff.ts)."""

from __future__ import annotations

import difflib
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DiffString:
    diff: str
    first_changed_line: int | None


def _split_lines(text: str) -> list[str]:
    if not text:
        return []
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    return lines


def generate_diff_string(
    old_content: str,
    new_content: str,
    context_lines: int = 4,
) -> DiffString:
    """Line-oriented display diff with upstream ``-N``/``+N`` markers."""
    old_lines = _split_lines(old_content)
    new_lines = _split_lines(new_content)
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines)
    opcodes = matcher.get_opcodes()
    width = len(str(max(len(old_lines), len(new_lines))))

    output: list[str] = []
    first_changed_line: int | None = None
    last_was_change = False

    def emit_context(line: str, number: int) -> None:
        output.append(f" {str(number).rjust(width)} {line}")

    def emit_removed(line: str, number: int) -> None:
        output.append(f"-{str(number).rjust(width)} {line}")

    def emit_added(line: str, number: int) -> None:
        output.append(f"+{str(number).rjust(width)} {line}")

    def emit_omitted() -> None:
        output.append(f" {' ' * width} ...")

    for index, (tag, i1, i2, j1, j2) in enumerate(opcodes):
        if tag == "equal":
            count = i2 - i1
            next_is_change = index < len(opcodes) - 1 and opcodes[index + 1][0] != "equal"
            if last_was_change and next_is_change and count > context_lines * 2:
                for row in range(i1, i1 + context_lines):
                    emit_context(old_lines[row], row + 1)
                emit_omitted()
                for row in range(i2 - context_lines, i2):
                    emit_context(old_lines[row], row + 1)
            elif last_was_change:
                shown = min(count, context_lines)
                for row in range(i1, i1 + shown):
                    emit_context(old_lines[row], row + 1)
                if count > shown:
                    emit_omitted()
            elif next_is_change:
                skipped = max(0, count - context_lines)
                if skipped:
                    emit_omitted()
                for row in range(i1 + skipped, i2):
                    emit_context(old_lines[row], row + 1)
            last_was_change = False
        else:
            if first_changed_line is None:
                first_changed_line = j1 + 1
            for row in range(i1, i2):
                emit_removed(old_lines[row], row + 1)
            for row in range(j1, j2):
                emit_added(new_lines[row], row + 1)
            last_was_change = True
    return DiffString(diff="\n".join(output), first_changed_line=first_changed_line)


def generate_unified_patch(
    path: str,
    old_content: str,
    new_content: str,
    context_lines: int = 4,
) -> str:
    """Unified diff with ``---``/``+++`` file headers only (no timestamps)."""
    return "\n".join(
        difflib.unified_diff(
            _split_lines(old_content),
            _split_lines(new_content),
            fromfile=path,
            tofile=path,
            lineterm="",
            n=context_lines,
        )
    )


__all__ = ["DiffString", "generate_diff_string", "generate_unified_patch"]
