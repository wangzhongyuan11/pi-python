"""Tool descriptions carry upstream-aligned truncation guidance (P11.5-T18)."""

from __future__ import annotations

from pathlib import Path

from pi_coding_agent.tools.registry import create_all_tools


def _descriptions(tmp_path: Path) -> dict[str, str]:
    tools = create_all_tools(
        cwd=tmp_path, tool_names=("read", "bash", "edit", "write", "grep", "find", "ls")
    )
    return {tool.name: tool.description for tool in tools}


def test_read_description_states_truncation_and_images(tmp_path: Path) -> None:
    text = _descriptions(tmp_path)["read"]
    assert "images (jpg, png, gif, webp, bmp)" in text
    assert "truncated to 2000 lines or 50KB" in text
    assert "offset" in text


def test_bash_description_states_tail_truncation_and_temp_file(tmp_path: Path) -> None:
    text = _descriptions(tmp_path)["bash"]
    assert "truncated to last 2000 lines or 50KB" in text
    assert "temp file" in text
    assert "timeout in seconds" in text


def test_edit_description_states_uniqueness(tmp_path: Path) -> None:
    text = _descriptions(tmp_path)["edit"]
    assert "must be unique in the original file" in text
    assert "must not overlap" in text


def test_write_description_states_parent_directories(tmp_path: Path) -> None:
    text = _descriptions(tmp_path)["write"]
    assert "Creates the file if it doesn't exist" in text
    assert "parent directories" in text


def test_grep_description_states_gitignore_and_limits(tmp_path: Path) -> None:
    text = _descriptions(tmp_path)["grep"]
    assert "Respects .gitignore" in text
    assert "truncated to 100 matches or 50KB" in text
    assert "truncated to 500 chars" in text


def test_find_description_states_gitignore_and_limit(tmp_path: Path) -> None:
    text = _descriptions(tmp_path)["find"]
    assert "Respects .gitignore" in text
    assert "truncated to 1000 results or 50KB" in text


def test_ls_description_states_sorting_and_limit(tmp_path: Path) -> None:
    text = _descriptions(tmp_path)["ls"]
    assert "sorted alphabetically" in text
    assert "'/' suffix for directories" in text
    assert "truncated to 500 entries or 50KB" in text
