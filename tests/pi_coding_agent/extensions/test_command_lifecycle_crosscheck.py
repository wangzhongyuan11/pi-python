"""Extension slash-command dispatch across session lifecycle transitions (P15).

Cross-validates the extension command registry (P14-T07) against the session
lifecycle (P14-T05/P14-T09): commands keep dispatching to the *current*
generation and session after reload and new-session, and the session name they
set lands in the session file that was active when the command ran.
"""

from __future__ import annotations

import asyncio
from io import StringIO
from pathlib import Path
from typing import Any

from pi_ai import FakeProvider, fake_assistant_message
from pi_coding_agent.cli.main import main
from pi_coding_agent.deepseek_credentials import DeepSeekCredentialResolver
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.session.catalog import open_session
from pi_coding_agent.session.models import SessionInfoEntry
from pi_coding_agent.tui.runner import InteractiveOptions, run_interactive

REPO = Path(__file__).resolve().parents[3]
GOLDEN_PACKAGE = REPO / "tests" / "fixtures" / "golden_package"

NOTE_EXTENSION_MANIFEST = '{"name":"note-extension","version":"1.0.0","entry":"main.py"}'
NOTE_EXTENSION_MAIN = """def activate(api):
    async def note(args, context):
        context.set_session_name(f"sim-{args.strip()}")
        return "sim-noted"

    api.define_command("sim-note", note)
    return lambda: None
"""


def test_extension_commands_stay_bound_across_reload_and_new_session(
    tmp_path: Path, monkeypatch: Any
) -> None:
    project = tmp_path / "project"
    agent_dir = tmp_path / "agent"
    session_dir = tmp_path / "sessions"
    project.mkdir()
    monkeypatch.setenv("PI_PYTHON_AGENT_DIR", str(agent_dir))
    assert (
        main(
            ["install", str(GOLDEN_PACKAGE)],
            stdout=StringIO(),
            stderr=StringIO(),
            cwd=project,
            environ={"PI_PYTHON_AGENT_DIR": str(agent_dir)},
        )
        == 0
    )
    extension_root = project / ".pi-python" / "extensions" / "note-extension"
    extension_root.mkdir(parents=True)
    (extension_root / "pi-extension.json").write_text(NOTE_EXTENSION_MANIFEST, encoding="utf-8")
    (extension_root / "main.py").write_text(NOTE_EXTENSION_MAIN, encoding="utf-8")

    # A session file is created with its first assistant message (upstream
    # parity), so run one turn per session before naming it via the command.
    provider = FakeProvider(
        [fake_assistant_message("first reply"), fake_assistant_message("second reply")]
    )
    replies = iter(
        (
            "hello",
            "/sim-note alpha",
            "/golden-reload",
            "/sim-note beta",
            "/golden-new",
            "/sim-note gamma",
            "again",
            "/exit",
        )
    )

    async def read_line(_prompt: str) -> str | None:
        return next(replies, None)

    output = StringIO()
    errors = StringIO()
    exit_code = asyncio.run(
        run_interactive(
            InteractiveOptions(
                cwd=project,
                credential_resolver=DeepSeekCredentialResolver(environ={}, cwd=project),
                model_runtime=ModelRuntime(provider=provider, model=provider.models[0]),
                session_dir=session_dir,
                project_trusted=True,
            ),
            stdout=output,
            stderr=errors,
            read_line=read_line,
        )
    )

    transcript = output.getvalue()
    assert exit_code == 0, errors.getvalue()
    assert transcript.count("sim-noted") == 3
    assert "golden-reloaded" in transcript
    assert "golden-new-session" in transcript
    assert "first reply" in transcript
    assert "second reply" in transcript
    assert errors.getvalue() == ""
    assert provider.call_count == 2

    files = list(session_dir.glob("*.jsonl"))
    assert len(files) == 2, f"expected original and replacement sessions, got {files}"

    def names(path: Path) -> list[str]:
        manager = open_session(path)
        return [
            entry.name
            for entry in manager.entries
            if isinstance(entry, SessionInfoEntry) and entry.name is not None
        ]

    assert len(files) == 2
    replacements = [path for path in files if open_session(path).header.parent_session]
    assert len(replacements) == 1, "the /golden-new session must reference its parent"
    replacement = replacements[0]
    original = next(path for path in files if path != replacement)
    # Commands issued before /golden-new belong to the original session; the
    # one issued afterwards belongs to the replacement session.
    assert names(original) == ["sim-alpha", "sim-beta"]
    assert names(replacement) == ["sim-gamma"]
