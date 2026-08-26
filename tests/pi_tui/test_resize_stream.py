from __future__ import annotations

from pi_tui.application import Application
from pi_tui.components import Status, Text, VStack
from pi_tui.render import ScreenRenderer
from pi_tui.testing import MemoryTerminal
from pi_tui.width import visible_width


def _three_lines() -> VStack:
    return VStack(
        Text("alpha", padding_x=0, padding_y=0),
        Text("bravo", padding_x=0, padding_y=0),
        Text("charlie", padding_x=0, padding_y=0),
        gap=0,
    )


def _output(terminal: MemoryTerminal) -> str:
    return "".join(terminal.output)


def _app(root: VStack, *, fullscreen: bool = False) -> tuple[MemoryTerminal, Application]:
    terminal = MemoryTerminal()
    terminal.start(lambda _data: None, lambda: None)
    return terminal, Application(terminal, root, fullscreen=fullscreen)


def test_first_render_writes_every_line_after_clearing() -> None:
    terminal, app = _app(_three_lines())

    app.render()

    screen = _output(terminal)
    assert "\x1b[2J\x1b[H" in screen
    assert "alpha" in screen and "bravo" in screen and "charlie" in screen


def test_rerender_without_changes_writes_nothing() -> None:
    terminal, app = _app(_three_lines())
    app.render()
    writes_before = len(terminal.output)

    app.render()

    assert len(terminal.output) == writes_before


def test_partial_update_rewrites_only_the_dirty_line() -> None:
    root = _three_lines()
    terminal, app = _app(root)
    app.render()
    baseline = "".join(terminal.output)

    root.add(Status("delta"))
    app.render()

    screen = _output(terminal)[len(baseline) :]
    assert "charlie" not in screen
    assert "delta" in screen
    assert "\x1b[K" in screen


def test_partial_update_returns_to_column_zero_before_replacing_line() -> None:
    root = Status("abc")
    terminal = MemoryTerminal()
    terminal.start(lambda _data: None, lambda: None)
    app = Application(terminal, root)
    app.render()
    baseline = _output(terminal)

    root.set_text("x")
    app.render()

    assert _output(terminal)[len(baseline) :] == "\r\x1b[Kx" + " " * 79


def test_resize_invalidates_and_repaints_full_screen() -> None:
    terminal, app = _app(_three_lines())
    app.render()
    baseline = "".join(terminal.output)

    terminal.resize(columns=40, rows=24)
    app.handle_resize()

    screen = _output(terminal)[len(baseline) :]
    assert screen.count("\x1b[2J\x1b[H") == 1
    assert "alpha" in screen and "bravo" in screen and "charlie" in screen
    repainted = screen.rsplit("\x1b[2J\x1b[H", 1)[1]
    assert all(len(line) <= 40 for line in repainted.split("\r\n"))


def test_fullscreen_mode_clips_to_terminal_rows() -> None:
    children = [Text(f"line{index}", padding_x=0, padding_y=0) for index in range(5)]
    terminal = MemoryTerminal(columns=20, rows=3)
    terminal.start(lambda _data: None, lambda: None)
    app = Application(terminal, VStack(*children, gap=0), fullscreen=True)

    app.render()

    screen = _output(terminal)
    assert "line2" in screen and "line3" in screen and "line4" in screen
    assert "line0" not in screen and "line1" not in screen


def test_application_sanitizes_and_bounds_custom_component_output() -> None:
    class UnsafeComponent:
        def render(self, width: int) -> tuple[str, ...]:
            del width
            return ("中文中文\x1b[2J",)

    terminal = MemoryTerminal(columns=4)
    terminal.start(lambda _data: None, lambda: None)
    app = Application(terminal, UnsafeComponent())

    app.render()

    rendered = _output(terminal).removeprefix("\x1b[2J\x1b[H")
    assert rendered == "中文"
    assert visible_width(rendered) == 4


def test_renderer_commit_freezes_lines_and_starts_fresh_below() -> None:
    terminal = MemoryTerminal(columns=20, rows=10)
    terminal.start(lambda _data: None, lambda: None)
    renderer = ScreenRenderer(terminal)

    renderer.render(("a",))
    renderer.commit()
    renderer.render(("b",))

    assert _output(terminal) == "\x1b[2J\x1b[Ha\x1b[1B\x1b[1B\r\x1b[Kb"
