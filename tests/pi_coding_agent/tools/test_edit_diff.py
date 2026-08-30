"""Edit diff and patch details (P11.5-T10)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from pi_coding_agent.tools.edit import Edit, edit_file
from pi_coding_agent.tools.edit_diff import generate_diff_string, generate_unified_patch
from pi_coding_agent.tools.registry import create_all_tools


class TestDiffString:
    def test_single_replacement_shows_removed_and_added_lines(self) -> None:
        old = "alpha\nbeta\ngamma\n"
        new = "alpha\nBETA\ngamma\n"
        result = generate_diff_string(old, new)
        diff, first = result.diff, result.first_changed_line
        assert first == 2
        assert "-2 beta" in diff
        assert "+2 BETA" in diff
        assert " 1 alpha" in diff

    def test_unchanged_content_has_no_first_changed_line(self) -> None:
        result = generate_diff_string("same\n", "same\n")
        assert result.diff == ""
        assert result.first_changed_line is None

    def test_line_numbers_are_padded_to_the_wider_file(self) -> None:
        old = "\n".join(f"line{i}" for i in range(12)) + "\n"
        new = old.replace("line3", "LINE3")
        result = generate_diff_string(old, new)
        diff = result.diff
        assert "- 4 line3" in diff
        assert "+ 4 LINE3" in diff


class TestUnifiedPatch:
    def test_patch_contains_hunk_headers_and_both_directions(self) -> None:
        old = "alpha\nbeta\ngamma\n"
        new = "alpha\nBETA\ngamma\n"
        patch = generate_unified_patch("src/file.py", old, new)
        assert "@@" in patch
        assert "-beta" in patch
        assert "+BETA" in patch
        assert " alpha" in patch


class TestEditResultDetails:
    def test_edit_file_reports_diff_patch_and_first_changed_line(self, tmp_path: Path) -> None:
        target = tmp_path / "file.txt"
        target.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
        result = asyncio.run(
            edit_file(target, [Edit(old_text="beta", new_text="BETA")], cwd=tmp_path)
        )
        assert result.first_changed_line == 2
        assert "-2 beta" in result.diff
        assert "+2 BETA" in result.diff
        assert "@@" in result.patch

    def test_registry_details_expose_diff_patch_and_first_changed_line(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "file.txt").write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
        (edit_tool,) = create_all_tools(cwd=tmp_path, tool_names=("edit",))
        params = edit_tool.validate_arguments(
            {"path": "file.txt", "edits": [{"oldText": "beta", "newText": "BETA"}]}
        )
        result = asyncio.run(edit_tool.execute("call-edit", params))
        details = result.details
        assert isinstance(details, dict)
        assert isinstance(details["diff"], str) and "beta" in details["diff"]
        assert isinstance(details["patch"], str) and "@@" in details["patch"]
        assert details["firstChangedLine"] == 2
