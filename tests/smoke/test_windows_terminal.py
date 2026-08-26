"""Terminal smoke checks, including a real subprocess run of the product loop."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

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


_CHILD_SCRIPT = textwrap.dedent(
    """
    import asyncio
    import os
    import sys
    from pathlib import Path

    from pi_ai import FakeProvider, fake_assistant_message
    from pi_coding_agent.deepseek_credentials import DeepSeekCredentialResolver
    from pi_coding_agent.model_runtime import ModelRuntime
    from pi_coding_agent.tui.runner import InteractiveOptions, run_interactive


    async def main() -> int:
        provider = FakeProvider([fake_assistant_message("子进程你好")])
        runtime = ModelRuntime(provider=provider, model=provider.models[0])
        loop = asyncio.get_running_loop()

        async def read_line(prompt: str) -> str | None:
            raw = await loop.run_in_executor(None, sys.stdin.readline)
            if not raw:
                return None
            stripped = raw.rstrip("\\n")
            return stripped or None

        cwd = Path(os.environ["PI_PYTHON_SMOKE_CWD"])
        return await run_interactive(
            InteractiveOptions(
                cwd=cwd,
                credential_resolver=DeepSeekCredentialResolver(environ={}, cwd=cwd),
                model_runtime=runtime,
                no_session=True,
            ),
            stdout=sys.stdout,
            stderr=sys.stderr,
            read_line=read_line,
        )

    raise SystemExit(asyncio.run(main()))
    """
)


@pytest.mark.skipif(sys.platform != "win32", reason="the real-terminal smoke runs on Windows")
def test_windows_terminal_smoke_drives_the_product_loop_in_a_real_process(
    tmp_path: Path,
) -> None:
    script = tmp_path / "smoke_child.py"
    script.write_text(_CHILD_SCRIPT, encoding="utf-8")
    env = {
        **os.environ,
        "PI_PYTHON_SMOKE_CWD": str(tmp_path),
        "PYTHONIOENCODING": "utf-8",
    }

    completed = subprocess.run(  # noqa: S603
        [sys.executable, str(script)],
        input="你好\n/exit\n",
        capture_output=True,
        encoding="utf-8",
        cwd=tmp_path,
        env=env,
        timeout=120,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "子进程你好" in completed.stdout
    assert "\x1b]52" not in completed.stdout
    assert "\x1b[" in completed.stdout
    assert completed.stderr == ""


@pytest.mark.skipif(sys.platform != "win32", reason="the PowerShell extension is Windows-only")
def test_powershell_extension_becomes_available_when_enabled_on_windows() -> None:
    from pi_coding_agent.builtin_extensions.powershell import PowerShellExtension

    extension = PowerShellExtension()
    extension.enable()

    assert extension.available is True
