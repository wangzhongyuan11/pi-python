from __future__ import annotations

from pi_coding_agent.tui.render_status import RetryStatusLine, SessionStatusLine
from pi_coding_agent.tui.render_tools import ToolExecutionView
from pi_tui.width import visible_width


def test_tool_view_transitions_in_place_through_lifecycle() -> None:
    view = ToolExecutionView("bash")

    running = view.render(24)
    assert any("bash" in line and "running" in line for line in running)

    view.complete("exit=0")
    done = view.render(24)
    assert done != running
    assert any("done" in line and "exit=0" in line for line in done)

    view.fail("timeout")
    failed = view.render(24)
    assert any("failed" in line for line in failed)


def test_parallel_tool_views_keep_distinct_rows() -> None:
    first = ToolExecutionView("read")
    second = ToolExecutionView("grep")
    second.fail("no matches")

    rows = [line.strip() for line in (*first.render(30), *second.render(30))]

    assert sum("running" in row for row in rows) == 1
    assert sum("failed" in row for row in rows) == 1


def test_retry_status_line_reports_attempts_and_delay() -> None:
    status = RetryStatusLine()
    lines = status.retry_started(attempt=2, max_attempts=3, delay_seconds=4.0).render(40)

    text = " ".join(line.strip() for line in lines)
    assert "retry 2/3" in text
    assert "4000ms" in text

    settled = status.retry_finished(success=True).render(40)
    assert any("recovered" in line.strip() for line in settled)


def test_compaction_status_line_reports_progress_and_done() -> None:
    status = SessionStatusLine()
    assert any("compacting" in line for line in status.compaction_started().render(40))
    assert any(
        "compacted" in line and "1200" in line
        for line in status.compaction_finished(tokens_before=1200).render(40)
    )


def test_status_lines_respect_terminal_cell_width_for_cjk() -> None:
    status = SessionStatusLine().activity("处理中：中文状态")

    lines = status.render(10)

    assert lines
    assert all(visible_width(line) <= 10 for line in lines)
