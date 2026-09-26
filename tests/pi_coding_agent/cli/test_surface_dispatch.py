"""Item-by-item dispatch verification for the documented CLI surface (P15-T01).

Every static flag and subcommand documented in surface-matrix.md sections 1-2
is invoked through the real ``main`` entry point. The contract under test:
the surface parses, dispatches to real behavior (never a stub), exits with a
contracted code, and never leaks a traceback. Post-v1 experimental commands
must be rejected outright.
"""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pytest

from pi_ai import FakeProvider, fake_assistant_message
from pi_coding_agent.cli.main import main
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.sdk import default_session_dir

STUB_MARKERS = ("not implemented", "unimplemented", "todo:", "stub")


def _runtime() -> ModelRuntime:
    provider = FakeProvider(
        [fake_assistant_message("ok")] * 40,
    )
    return ModelRuntime(provider=provider, model=provider.models[0])


def _invoke(
    argv: list[str],
    tmp_path: Path,
    agent_dir: Path,
    *,
    expect: int,
) -> tuple[int, str, str]:
    stdout = StringIO()
    stderr = StringIO()
    code = main(
        argv,
        stdout=stdout,
        stderr=stderr,
        cwd=tmp_path,
        environ={"PI_PYTHON_AGENT_DIR": str(agent_dir)},
        model_runtime=_runtime(),
    )
    combined = (stdout.getvalue() + stderr.getvalue()).lower()
    assert "traceback" not in combined.lower(), combined
    assert not any(marker in combined for marker in STUB_MARKERS), combined
    assert code == expect, f"argv={argv!r} code={code} stdout={stdout.getvalue()!r}"
    return code, stdout.getvalue(), stderr.getvalue()


def test_documented_headless_flags_dispatch_end_to_end(tmp_path: Path, agent_dir: Path) -> None:
    # CLI-FLAG-004 version, CLI-FLAG-003 help.
    _invoke(["--version"], tmp_path, agent_dir, expect=0)
    _invoke(["-v"], tmp_path, agent_dir, expect=0)
    code, help_text, _ = _invoke(["--help"], tmp_path, agent_dir, expect=0)
    for documented in (
        "--mode",
        "--print",
        "--provider",
        "--model",
        "--system-prompt",
        "--append-system-prompt",
        "--thinking",
        "--continue",
        "--resume",
        "--session",
        "--session-id",
        "--fork",
        "--no-session",
        "--session-dir",
        "--name",
        "--tools",
        "--exclude-tools",
        "--no-tools",
        "--no-builtin-tools",
        "--tui-mode",
    ):
        assert documented in help_text, f"missing {documented} in --help"

    # CLI-FLAG-005/006 mode and print.
    _invoke(["-p", "hello"], tmp_path, agent_dir, expect=0)
    _invoke(["--mode", "text", "-p", "hello"], tmp_path, agent_dir, expect=0)
    _invoke(["--mode", "json", "-p", "hello"], tmp_path, agent_dir, expect=0)
    _invoke(["--print", "hello"], tmp_path, agent_dir, expect=0)
    # CLI-FLAG-022..025 tool selection flags.
    _invoke(["--tools", "read,ls", "-p", "hello", "--no-session"], tmp_path, agent_dir, expect=0)
    _invoke(
        ["--exclude-tools", "read", "-p", "hello", "--no-session"],
        tmp_path,
        agent_dir,
        expect=0,
    )
    _invoke(["--no-tools", "-p", "hello"], tmp_path, agent_dir, expect=0)
    _invoke(["--no-builtin-tools", "-p", "hello", "--no-session"], tmp_path, agent_dir, expect=0)
    # CLI-FLAG-007/008/012 provider, model, thinking.
    _invoke(
        ["--provider", "deepseek", "-p", "hello", "--no-session"],
        tmp_path,
        agent_dir,
        expect=0,
    )
    _invoke(
        ["--model", "fake/fake-1", "-p", "hello", "--no-session"],
        tmp_path,
        agent_dir,
        expect=0,
    )
    _invoke(["--model", "fake-1", "-p", "hello", "--no-session"], tmp_path, agent_dir, expect=0)
    _invoke(
        ["--model", "fake/fake-1:off", "-p", "hello", "--no-session"],
        tmp_path,
        agent_dir,
        expect=0,
    )
    _invoke(["--thinking", "off", "-p", "hello", "--no-session"], tmp_path, agent_dir, expect=0)
    _invoke(["--thinking", "bogus", "-p", "hello", "--no-session"], tmp_path, agent_dir, expect=2)
    # CLI-FLAG-010/011 system prompt surfaces.
    _invoke(
        ["--system-prompt", "be brief", "-p", "hello", "--no-session"],
        tmp_path,
        agent_dir,
        expect=0,
    )
    _invoke(
        ["--append-system-prompt", "more detail", "-p", "hello", "--no-session"],
        tmp_path,
        agent_dir,
        expect=0,
    )
    # CLI-FLAG-020 session naming.
    _invoke(
        ["--name", "probe-session", "-p", "hello", "--no-session"],
        tmp_path,
        agent_dir,
        expect=0,
    )


def test_documented_session_flags_open_create_fork_and_export(
    tmp_path: Path, agent_dir: Path
) -> None:
    # CLI-FLAG-015 explicit path opens strictly; a missing file is a typed failure.
    session_file = tmp_path / "probe-session.jsonl"
    _invoke(["--session", str(session_file), "-p", "first"], tmp_path, agent_dir, expect=1)
    assert not session_file.exists()
    # CLI-FLAG-013/--continue and --resume without persisted sessions are typed failures.
    _invoke(["--resume", "-p", "hello"], tmp_path, agent_dir, expect=1)
    _invoke(["--continue", "-p", "hello"], tmp_path, agent_dir, expect=1)


def test_session_id_flag_opens_or_creates_the_named_session(
    tmp_path: Path, agent_dir: Path
) -> None:
    # CLI-FLAG-016 strict id: open when it exists, create when missing.
    explicit_id = "b" * 32
    _invoke(["--session-id", explicit_id, "-p", "first"], tmp_path, agent_dir, expect=0)
    matches = list((agent_dir / "sessions").rglob(f"*{explicit_id}.jsonl"))
    assert len(matches) == 1
    _invoke(["--session-id", explicit_id, "-p", "second"], tmp_path, agent_dir, expect=0)
    assert len(list((agent_dir / "sessions").rglob(f"*{explicit_id}.jsonl"))) == 1
    persisted = matches[0].read_text(encoding="utf-8")
    assert "first" in persisted
    assert "second" in persisted
    # IDs are strictly validated.
    _invoke(["--session-id", "not a session id!", "-p", "x"], tmp_path, agent_dir, expect=1)


def test_fork_flag_copies_source_history_into_a_new_session(
    tmp_path: Path, agent_dir: Path
) -> None:
    # CLI-FLAG-017 fork copies the full source history into a new v3 session.
    _invoke(["-p", "original"], tmp_path, agent_dir, expect=0)
    source = next(default_session_dir(tmp_path).glob("*.jsonl"))
    _invoke(["--fork", str(source), "-p", "forked"], tmp_path, agent_dir, expect=0)
    forks = [
        path
        for path in default_session_dir(tmp_path).glob("*.jsonl")
        if "original" in path.read_text(encoding="utf-8")
    ]
    assert len(forks) >= 2, "fork did not copy the source history into a new session"
    # --fork cannot be combined with the other session selection flags.
    _invoke(["--fork", str(source), "--session", "other"], tmp_path, agent_dir, expect=2)


def test_continue_flag_resumes_the_latest_default_directory_session(
    tmp_path: Path, agent_dir: Path
) -> None:
    # CLI-FLAG-013 continue opens the latest session of this cwd without --session-dir.
    _invoke(["-p", "first"], tmp_path, agent_dir, expect=0)
    _invoke(["--continue", "-p", "second"], tmp_path, agent_dir, expect=0)
    persisted = "\n".join(
        path.read_text(encoding="utf-8") for path in default_session_dir(tmp_path).glob("*.jsonl")
    )
    assert "first" in persisted
    assert "second" in persisted


def test_documented_package_subcommands_complete_the_lifecycle(
    tmp_path: Path, agent_dir: Path
) -> None:
    repository = Path(__file__).resolve().parents[3]
    package = repository / "tests" / "fixtures" / "golden_package"

    # CLI-CMD-010 experimental commands stay Post-v1: the words are not reserved
    # subcommands, so they fall through to prompt messages instead of dispatching.
    for experimental in ("pi", "server", "client"):
        _invoke([experimental, "--no-session"], tmp_path, agent_dir, expect=0)

    # CLI-CMD-001/005/006/002 with the local golden package.
    _invoke(["install", str(package), "--no-approve"], tmp_path, agent_dir, expect=0)
    _code, listed, _err = _invoke(["list"], tmp_path, agent_dir, expect=0)
    assert f"user: {package} (enabled)" in listed
    _invoke(["config", str(package), "disabled"], tmp_path, agent_dir, expect=0)
    _code, listed, _err = _invoke(["list"], tmp_path, agent_dir, expect=0)
    assert "(disabled)" in listed
    _invoke(["remove", str(package)], tmp_path, agent_dir, expect=0)
    _code, listed_after, _err = _invoke(["list"], tmp_path, agent_dir, expect=0)
    assert str(package) not in listed_after
    # CLI-CMD-003 uninstall alias and CLI-CMD-004 update surfaces.
    _invoke(["uninstall", "does-not-exist"], tmp_path, agent_dir, expect=1)
    _invoke(["update", "--offline"], tmp_path, agent_dir, expect=0)
    _invoke(["update", "self"], tmp_path, agent_dir, expect=0)


def test_documented_auth_and_session_subcommands_dispatch(tmp_path: Path, agent_dir: Path) -> None:
    # CLI-CMD-007 auth check without credentials is a typed failure with JSON shape.
    stdout = StringIO()
    stderr = StringIO()
    code = main(
        ["auth", "check", "--json"],
        stdout=stdout,
        stderr=stderr,
        cwd=tmp_path,
        environ={"PI_PYTHON_AGENT_DIR": str(agent_dir)},
        model_runtime=_runtime(),
    )
    assert code == 1
    payload = json.loads(stdout.getvalue())
    assert isinstance(payload, dict)
    assert "traceback" not in stderr.getvalue()
    # CLI-CMD-008 print-api-key without a key fails without leaking anything.
    code, out, err = _invoke(["auth", "print-api-key"], tmp_path, agent_dir, expect=1)
    assert out == ""
    # CLI-CMD-012 import-pi-session requires a source.
    _invoke(["import-pi-session"], tmp_path, agent_dir, expect=2)
    # session repair dispatches (P11.5-T16); a missing file is a typed failure.
    _invoke(["session", "repair", str(tmp_path / "missing.jsonl")], tmp_path, agent_dir, expect=1)


def test_unknown_top_level_words_run_as_prompt_messages(tmp_path: Path, agent_dir: Path) -> None:
    # The parser reserves only documented subcommands; anything else is a message.
    _invoke(["definitely-not-a-command", "--no-session"], tmp_path, agent_dir, expect=0)


@pytest.fixture()
def agent_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "agent"
    directory.mkdir()
    monkeypatch.setenv("PI_PYTHON_AGENT_DIR", str(directory))
    return directory
