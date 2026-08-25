from __future__ import annotations

import sys

from pi_tui.components import Status, Text, VStack
from pi_tui.render import ScreenRenderer
from pi_tui.testing import MemoryTerminal
from pi_tui.width import visible_width


def test_windows_terminal_renders_cjk_within_width_in_process() -> None:
    terminal = MemoryTerminal(columns=80, rows=24)
    terminal.start(lambda _data: None, lambda: None)
    renderer = ScreenRenderer(terminal)

    view = VStack(Text("中文内容", padding_x=1, padding_y=0), Status("就绪"), gap=0)

    renderer.render(list(view.render(80)))

    screen = "".join(terminal.output)
    assert "中文内容" in screen and "就绪" in screen
    content_lines = [line for line in screen.split("\r\n") if line]
    assert all(visible_width(line) <= 80 for line in content_lines)


def test_current_platform_is_supported_or_windows_smoke_skipped() -> None:
    if sys.platform == "win32":
        from pi_coding_agent.builtin_extensions.powershell import PowerShellExtension

        extension = PowerShellExtension()
        extension.enable()
        assert extension.available is True
    else:
        assert sys.platform in {"linux"}
