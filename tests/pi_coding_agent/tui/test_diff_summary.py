"""Edit diff summary rendering in the product TUI (P11.5-T12)."""

from __future__ import annotations

from pi_ai import TextContent
from pi_coding_agent.tui.main import result_detail
from pi_coding_agent.tui.render_tools import ToolExecutionView, edit_diff_summary


def test_summary_counts_added_removed_and_first_changed_line() -> None:
    details = {
        "path": "file.txt",
        "replacements": 1,
        "diff": " 1 alpha\n-2 beta\n+2 BETA\n 3 gamma",
        "patch": "--- file.txt\n+++ file.txt\n@@ -1,3 +1,3 @@",
        "firstChangedLine": 2,
    }
    assert edit_diff_summary(details) == "1 block(s), +1 -1, line 2"


def test_summary_handles_multi_line_and_missing_first_line() -> None:
    details = {
        "replacements": 2,
        "diff": "-1 old\n-2 more\n+1 new\n+2 fresh\n+3 extra",
    }
    assert edit_diff_summary(details) == "2 block(s), +3 -2"


def test_summary_returns_none_for_non_edit_details() -> None:
    assert edit_diff_summary({"path": "x", "replacements": 1}) is None
    assert edit_diff_summary(None) is None


def test_tool_view_shows_the_diff_summary_after_edit_completes() -> None:
    view = ToolExecutionView("edit")
    view.complete("1 block(s), +1 -1, line 2")
    rendered = "\n".join(view.render(48))
    assert "+1 -1" in rendered


def testresult_detail_prefers_diff_summary_over_raw_dict() -> None:
    class _Result:
        details = {
            "path": "file.txt",
            "replacements": 1,
            "diff": " 1 alpha\n-2 beta\n+2 BETA\n 3 gamma",
            "patch": "@@",
            "firstChangedLine": 2,
        }
        content = (TextContent(text="Successfully replaced 1 block(s) in file.txt."),)

    detail = result_detail(_Result(), include_content=False)
    assert detail == "1 block(s), +1 -1, line 2"
