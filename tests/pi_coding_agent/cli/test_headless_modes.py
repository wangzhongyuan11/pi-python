from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

from pi_ai import FakeProvider, fake_assistant_message
from pi_ai.wire.messages import dump_message
from pi_coding_agent.cli.main import main
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.session.manager import SessionManager
from pi_coding_agent.session.models import MessageEntry


def _run(argv: list[str], cwd: Path, provider: FakeProvider) -> tuple[int, str, str]:
    stdout = StringIO()
    stderr = StringIO()
    code = main(
        argv,
        stdout=stdout,
        stderr=stderr,
        cwd=cwd,
        environ={},
        model_runtime=ModelRuntime(provider=provider, model=provider.models[0]),
    )
    return code, stdout.getvalue(), stderr.getvalue()


def _stored_session(cwd: Path, session_dir: Path) -> SessionManager:
    manager = SessionManager.create(
        cwd=cwd,
        session_dir=session_dir,
        session_id="stored-session",
        timestamp="2026-08-24T00:00:00.000Z",
    )
    manager.append(
        MessageEntry(
            type="message",
            id="previous",
            parent_id=None,
            timestamp="2026-08-24T00:00:01.000Z",
            message=dump_message(fake_assistant_message("previous", timestamp=1)),
        )
    )
    return manager


def test_text_mode_prints_only_final_assistant_text(tmp_path: Path) -> None:
    result = _run(
        ["--print", "--no-session", "explain", "this"],
        tmp_path,
        FakeProvider([fake_assistant_message("final answer")]),
    )

    assert result == (0, "final answer\n", "")


def test_json_mode_emits_only_jsonl_agent_events(tmp_path: Path) -> None:
    code, stdout, stderr = _run(
        ["--mode", "json", "--no-session", "hello"],
        tmp_path,
        FakeProvider([fake_assistant_message("json answer")]),
    )
    records = [json.loads(line) for line in stdout.splitlines()]

    assert code == 0
    assert stderr == ""
    assert records[0]["type"] == "agent_start"
    assert records[-1]["type"] == "agent_end"
    assert any(record["type"] == "message_end" for record in records)


def test_text_mode_maps_terminal_provider_error_without_traceback(tmp_path: Path) -> None:
    code, stdout, stderr = _run(
        ["--print", "--no-session", "hello"],
        tmp_path,
        FakeProvider(
            [fake_assistant_message((), stop_reason="error", error_message="safe failure")]
        ),
    )

    assert code == 1
    assert stdout == ""
    assert stderr == "safe failure\n"
    assert "Traceback" not in stderr


def test_conflicting_session_flags_are_usage_error(tmp_path: Path) -> None:
    code, stdout, stderr = _run(
        ["--no-session", "--session", "missing.jsonl", "hello"],
        tmp_path,
        FakeProvider(),
    )

    assert code == 2
    assert stdout == ""
    assert "not allowed with argument" in stderr


def test_explicit_session_and_resume_restore_history_into_provider_context(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions-explicit"
    stored = _stored_session(tmp_path, session_dir)
    resume_dir = tmp_path / "sessions-resume"
    _stored_session(tmp_path, resume_dir)
    assert stored.path is not None

    explicit_provider = FakeProvider([fake_assistant_message("explicit")])
    explicit = _run(
        ["--print", "--session", str(stored.path), "next"],
        tmp_path,
        explicit_provider,
    )
    resume_provider = FakeProvider([fake_assistant_message("resumed")])
    resumed = _run(
        ["--print", "--resume", "--session-dir", str(resume_dir), "again"],
        tmp_path,
        resume_provider,
    )

    assert explicit == (0, "explicit\n", "")
    assert resumed == (0, "resumed\n", "")
    assert [message.role for message in explicit_provider.calls[0][1].messages] == [
        "assistant",
        "user",
    ]
    assert [message.role for message in resume_provider.calls[0][1].messages] == [
        "assistant",
        "user",
    ]
