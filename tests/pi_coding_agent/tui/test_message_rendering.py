from __future__ import annotations

from pi_coding_agent.tui.render_messages import AssistantMessageView
from pi_tui.width import visible_width


def test_text_deltas_accumulate_into_wrapped_lines() -> None:
    view = AssistantMessageView()

    view.add_text_delta("The quick brown ")
    view.add_text_delta("fox jumps")
    lines = view.render(20)

    assert lines[0].strip().startswith("The quick brown fox")
    assert all(len(line) <= 20 for line in lines)
    assert " ".join(line.strip() for line in lines) == "The quick brown fox jumps"


def test_thinking_renders_as_distinct_prefixed_section_before_text() -> None:
    view = AssistantMessageView()
    view.add_thinking_delta("considering options")
    view.add_text_delta("Answer: yes")

    lines = [line.strip() for line in view.render(40)]

    assert any(line.startswith("thinking:") for line in lines)
    thinking_index = next(index for index, line in enumerate(lines) if line.startswith("thinking:"))
    answer_index = next(index for index, line in enumerate(lines) if line.startswith("Answer"))
    assert thinking_index < answer_index


def test_long_thinking_continuations_stay_within_terminal_width() -> None:
    view = AssistantMessageView()
    view.add_thinking_delta("需要逐项分析这个项目的架构与调用路径。" * 20)

    lines = view.render(79)

    assert len(lines) > 1
    assert all(visible_width(line) <= 79 for line in lines)
    assert all(line.startswith(" " * len("thinking: ")) for line in lines[1:])


def test_error_stop_reason_renders_error_line_and_stops_stream() -> None:
    view = AssistantMessageView()
    view.add_text_delta("partial output")
    view.fail("503 service unavailable")

    lines = [line.strip() for line in view.render(60)]

    assert any("[error] 503 service unavailable" in line for line in lines)
    assert view.failed is True
