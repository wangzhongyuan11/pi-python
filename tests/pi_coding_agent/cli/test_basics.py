from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import TextIO

import pytest

from pi_coding_agent import __version__
from pi_coding_agent.cli.main import main
from pi_coding_agent.tui.runner import InteractiveOptions


def _run(
    argv: list[str],
    *,
    cwd: Path,
    environ: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    stdout = StringIO()
    stderr = StringIO()
    code = main(
        argv,
        stdout=stdout,
        stderr=stderr,
        cwd=cwd,
        environ={} if environ is None else environ,
    )
    return code, stdout.getvalue(), stderr.getvalue()


def test_help_version_and_usage_exit_codes(tmp_path: Path) -> None:
    help_code, help_out, help_err = _run(["--help"], cwd=tmp_path)
    version_code, version_out, version_err = _run(["--version"], cwd=tmp_path)
    bad_code, bad_out, bad_err = _run(["--unknown"], cwd=tmp_path)

    assert help_code == 0
    assert "usage: pi-python" in help_out
    assert help_err == ""
    assert version_code == 0
    assert version_out == f"pi-python {__version__}\n"
    assert version_err == ""
    assert bad_code == 2
    assert bad_out == ""
    assert "unrecognized arguments: --unknown" in bad_err


def test_list_models_uses_reviewed_deepseek_catalog(tmp_path: Path) -> None:
    code, stdout, stderr = _run(["--list-models"], cwd=tmp_path)

    assert code == 0
    assert stdout.splitlines() == [
        "deepseek/deepseek-v4-flash\tDeepSeek V4 Flash",
        "deepseek/deepseek-v4-pro\tDeepSeek V4 Pro (default)",
    ]
    assert stderr == ""


def test_auth_check_never_prints_key_and_explicit_print_command_does(tmp_path: Path) -> None:
    secret = "test-secret-value"
    missing = _run(["auth", "check"], cwd=tmp_path)
    ready = _run(["auth", "check", "--json"], cwd=tmp_path, environ={"DEEPSEEK_API_KEY": secret})
    printed = _run(
        ["auth", "print-api-key"],
        cwd=tmp_path,
        environ={"DEEPSEEK_API_KEY": secret},
    )

    assert missing[0] == 1
    assert secret not in missing[1] + missing[2]
    assert ready == (0, '{"provider":"deepseek","ready":true}\n', "")
    assert secret not in ready[1] + ready[2]
    assert printed == (0, f"{secret}\n", "")


def test_global_api_key_before_auth_command_is_not_treated_as_a_prompt(tmp_path: Path) -> None:
    secret = "explicit-secret"

    result = _run(
        ["--api-key", secret, "auth", "check", "--json"],
        cwd=tmp_path,
    )

    assert result == (0, '{"provider":"deepseek","ready":true}\n', "")
    assert secret not in result[1] + result[2]


def test_no_prompt_enters_interactive_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import pi_coding_agent.cli.main as cli_main

    calls: list[Path] = []

    async def interactive(
        options: InteractiveOptions,
        *,
        stdout: TextIO,
        stderr: TextIO,
    ) -> int:
        del stdout, stderr
        calls.append(options.cwd)
        return 0

    monkeypatch.setattr(cli_main, "run_interactive", interactive)

    assert _run([], cwd=tmp_path) == (0, "", "")
    assert calls == [tmp_path.resolve()]
