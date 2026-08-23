from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from pi_coding_agent.tools.edit import Edit, EditToolError, edit_file


def test_applies_disjoint_edits_against_original_and_preserves_bom_crlf(tmp_path: Path) -> None:
    path = tmp_path / "sample.txt"
    original = "\ufeffalpha\r\n中文\r\nomega\r\n"
    path.write_bytes(original.encode("utf-8"))

    result = asyncio.run(
        edit_file(
            path,
            [Edit(old_text="alpha\n中文", new_text="A\n中"), Edit(old_text="omega", new_text="Ω")],
            cwd=tmp_path,
        )
    )

    assert path.read_bytes() == "\ufeffA\r\n中\r\nΩ\r\n".encode()
    assert result.replacements == 2


@pytest.mark.parametrize(
    ("edits", "message"),
    [
        ([Edit(old_text="missing", new_text="new")], "Could not find"),
        ([Edit(old_text="same", new_text="new")], "2 occurrences"),
        (
            [
                Edit(old_text="alpha beta", new_text="first"),
                Edit(old_text="beta", new_text="second"),
            ],
            "overlap",
        ),
    ],
)
def test_invalid_edit_batch_leaves_original_bytes_unchanged(
    tmp_path: Path, edits: list[Edit], message: str
) -> None:
    path = tmp_path / "sample.txt"
    original = b"alpha beta same same\n"
    path.write_bytes(original)

    with pytest.raises(EditToolError, match=message):
        asyncio.run(edit_file(path, edits, cwd=tmp_path))

    assert path.read_bytes() == original


def test_rejects_empty_batch_empty_target_and_no_change(tmp_path: Path) -> None:
    path = tmp_path / "sample.txt"
    path.write_text("alpha", encoding="utf-8")

    for edits, message in (
        ([], "at least one"),
        ([Edit(old_text="", new_text="x")], "must not be empty"),
        ([Edit(old_text="alpha", new_text="alpha")], "No changes"),
    ):
        with pytest.raises(EditToolError, match=message):
            asyncio.run(edit_file(path, edits, cwd=tmp_path))

    assert path.read_text(encoding="utf-8") == "alpha"


def test_abort_before_edit_preserves_file(tmp_path: Path) -> None:
    path = tmp_path / "sample.txt"
    path.write_text("old", encoding="utf-8")
    abort_event = asyncio.Event()
    abort_event.set()

    with pytest.raises(EditToolError, match="aborted"):
        asyncio.run(
            edit_file(
                path,
                [Edit(old_text="old", new_text="new")],
                cwd=tmp_path,
                abort_event=abort_event,
            )
        )

    assert path.read_text(encoding="utf-8") == "old"
