"""Session naming via --name and session_info entries (P11.5-T15)."""

from __future__ import annotations

import asyncio
from io import StringIO
from pathlib import Path

from pi_ai import FakeProvider, fake_assistant_message
from pi_coding_agent.cli.main import main
from pi_coding_agent.deepseek_credentials import DeepSeekCredentialResolver
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.session.catalog import list_sessions
from pi_coding_agent.session.manager import SessionManager
from pi_coding_agent.session.models import SessionInfoEntry
from pi_coding_agent.tui.runner import InteractiveOptions, run_interactive


def _ids() -> list[str]:
    return [f"entry-{i}" for i in range(10)]


def test_append_session_info_sanitizes_and_appends(tmp_path: Path) -> None:
    manager = SessionManager.create(
        cwd=tmp_path,
        session_dir=tmp_path,
        session_id="0123456789abcdef0123456789abcdef",
        timestamp="2026-08-30T00:00:00.000Z",
    )
    ids = iter(_ids())
    entry_id = manager.append_session_info(
        "line one\nline two",
        entry_id_factory=lambda: next(ids),
        timestamp_factory=lambda: "2026-08-30T00:00:01.000Z",
    )
    assert entry_id == "entry-0"
    entry = manager.entries[-1]
    assert isinstance(entry, SessionInfoEntry)
    assert entry.name == "line one line two"
    assert manager.leaf_id == "entry-0"


def test_cli_name_flag_persists_session_info(tmp_path: Path) -> None:
    provider = FakeProvider([fake_assistant_message("hello there")])
    runtime = ModelRuntime(provider=provider, model=provider.models[0])
    session_dir = tmp_path / "sessions"
    code = main(
        ["--name", "  probe   run ", "--session-dir", str(session_dir), "-p", "hi"],
        stdout=StringIO(),
        stderr=StringIO(),
        cwd=tmp_path,
        environ={},
        model_runtime=runtime,
    )
    assert code == 0
    catalog = list_sessions(cwd=tmp_path, session_dir=session_dir)
    assert catalog.sessions[0].name == "probe run"


def test_cli_rejects_blank_name(tmp_path: Path) -> None:
    provider = FakeProvider([])
    runtime = ModelRuntime(provider=provider, model=provider.models[0])
    errors = StringIO()
    code = main(
        ["--name", "   ", "--session-dir", str(tmp_path / "s"), "-p", "hi"],
        stdout=StringIO(),
        stderr=errors,
        cwd=tmp_path,
        environ={},
        model_runtime=runtime,
    )
    assert code == 1
    assert "non-empty" in errors.getvalue()


def test_interactive_name_flag_persists_session_info(tmp_path: Path) -> None:
    provider = FakeProvider([fake_assistant_message("reply")])
    runtime = ModelRuntime(provider=provider, model=provider.models[0])
    session_dir = tmp_path / "sessions"
    replies = iter(("hello", "/exit"))
    output = StringIO()

    async def read_line(_prompt: str) -> str | None:
        return next(replies, None)

    code = asyncio.run(
        run_interactive(
            InteractiveOptions(
                cwd=tmp_path,
                credential_resolver=DeepSeekCredentialResolver(environ={}, cwd=tmp_path),
                model_runtime=runtime,
                session_dir=session_dir,
                name="tui session",
            ),
            stdout=output,
            stderr=StringIO(),
            read_line=read_line,
        )
    )
    assert code == 0
    catalog = list_sessions(cwd=tmp_path, session_dir=session_dir)
    assert catalog.sessions[0].name == "tui session"
