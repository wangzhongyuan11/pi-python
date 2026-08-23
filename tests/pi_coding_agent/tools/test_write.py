from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from pi_coding_agent.tools.write import WriteToolError, write_file


def test_creates_parent_directories_and_writes_exact_utf8_bytes(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "中文.txt"
    content = "\ufeffalpha\r\n中文\r\n"

    result = asyncio.run(write_file(path, content, cwd=tmp_path))

    assert path.read_bytes() == content.encode("utf-8")
    assert result.path == path.resolve()
    assert result.bytes_written == len(content.encode("utf-8"))


def test_atomically_replaces_existing_content_without_temp_residue(tmp_path: Path) -> None:
    path = tmp_path / "existing.txt"
    path.write_bytes(b"old")
    entries_before = set(tmp_path.iterdir())

    asyncio.run(write_file(path, "new\ncontent", cwd=tmp_path))

    assert path.read_bytes() == b"new\ncontent"
    assert set(tmp_path.iterdir()) == entries_before


def test_pre_aborted_write_does_not_create_parent_or_file(tmp_path: Path) -> None:
    path = tmp_path / "missing" / "file.txt"
    abort_event = asyncio.Event()
    abort_event.set()

    with pytest.raises(WriteToolError, match="aborted"):
        asyncio.run(write_file(path, "content", cwd=tmp_path, abort_event=abort_event))

    assert not path.parent.exists()


def test_write_follows_existing_symlink_target(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    target.write_text("old", encoding="utf-8")
    alias = tmp_path / "alias.txt"
    try:
        alias.symlink_to(target)
    except OSError as error:
        pytest.skip(f"symlink creation is unavailable: {error}")

    asyncio.run(write_file(alias, "new", cwd=tmp_path))

    assert target.read_text(encoding="utf-8") == "new"
    assert alias.is_symlink()
