from __future__ import annotations

import os
from pathlib import Path

import pytest

from pi_coding_agent.tools.operations import (
    DirectoryEntry,
    FilesystemOperations,
    ProcessOperations,
    SearchMatch,
    SearchOperations,
)
from pi_coding_agent.tools.paths import canonical_tool_path, resolve_tool_path


def test_operation_ports_and_result_values_are_importable() -> None:
    assert FilesystemOperations.__name__ == "FilesystemOperations"
    assert ProcessOperations.__name__ == "ProcessOperations"
    assert SearchOperations.__name__ == "SearchOperations"
    entry = DirectoryEntry(
        name="a b.txt",
        path=Path("a b.txt"),
        is_file=True,
        is_dir=False,
    )
    assert entry.name == "a b.txt"
    assert SearchMatch(path=Path("中文.txt"), line=2, column=3, text="命中").line == 2


def test_resolve_tool_path_handles_at_prefix_unicode_spaces_and_home(tmp_path: Path) -> None:
    cwd = tmp_path / "work tree"
    cwd.mkdir()
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)

    assert (
        resolve_tool_path("@folder\u202fname.txt", cwd=cwd, home=home)
        == (cwd / "folder name.txt").resolve()
    )
    assert (
        resolve_tool_path("~/config.json", cwd=cwd, home=home) == (home / "config.json").resolve()
    )


def test_canonical_path_resolves_symlink_aliases_and_missing_children(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(real, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlink creation is unavailable: {error}")

    real_file = real / "file.txt"
    real_file.write_text("x", encoding="utf-8")

    assert canonical_tool_path(real_file, cwd=tmp_path) == canonical_tool_path(
        alias / "file.txt", cwd=tmp_path
    )
    assert canonical_tool_path(real / "new.txt", cwd=tmp_path) == canonical_tool_path(
        alias / "new.txt", cwd=tmp_path
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows path case behavior")
def test_canonical_path_normalizes_windows_case(tmp_path: Path) -> None:
    path = tmp_path / "MixedCase.txt"
    path.write_text("x", encoding="utf-8")

    assert canonical_tool_path(path, cwd=tmp_path) == canonical_tool_path(
        Path(str(path).upper()), cwd=tmp_path
    )
