from __future__ import annotations

from io import StringIO
from pathlib import Path

from pi_coding_agent import __version__
from pi_coding_agent.cli.main import main


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
