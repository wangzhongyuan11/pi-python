"""P17-T03: escape-first HTML session export.

Script tags, ANSI escapes, and extension renderer output must never execute
or corrupt the exported document; the exporter port, CLI ``--export``, and
RPC ``export_html`` all produce the same escaped artifact.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from uuid import uuid4

from pi_ai import UserMessage, fake_assistant_message
from pi_ai.wire.messages import dump_message
from pi_coding_agent.export.html import HtmlSessionExporter, render_session_html
from pi_coding_agent.session.export import export_session
from pi_coding_agent.session.manager import SessionManager
from pi_coding_agent.session.models import CustomMessageEntry, MessageEntry


def _session_with(
    tmp_path: Path, texts: list[str], *, custom: tuple[str, str] | None = None
) -> SessionManager:
    manager = SessionManager.create(
        cwd=tmp_path,
        session_dir=tmp_path,
        session_id=f"export{uuid4().hex[:24]}",
        timestamp="2026-09-28T00:00:00.000Z",
    )
    index = 0

    def entry(message: object) -> MessageEntry:
        nonlocal index
        index += 1
        return MessageEntry(
            type="message",
            id=f"e{index:03d}",
            parent_id=manager.leaf_id,
            timestamp=f"2026-09-28T00:00:{index:02d}.000Z",
            message=dump_message(message),  # type: ignore[arg-type]
        )

    for text in texts:
        manager.append(entry(UserMessage(content=text, timestamp=index)))
        manager.append(entry(fake_assistant_message(f"reply {index}")))
    if custom is not None:
        custom_type, content = custom
        manager.append(
            CustomMessageEntry(
                type="custom_message",
                id=f"c{index:03d}",
                parent_id=manager.leaf_id,
                timestamp="2026-09-28T00:00:59.000Z",
                custom_type=custom_type,
                content=content,
                display=True,
                details=None,
            )
        )
    return manager


def test_export_renders_messages_without_executable_content(tmp_path: Path) -> None:
    manager = _session_with(tmp_path, ["hello world"])

    html = render_session_html(export_session(manager))

    assert "hello world" in html
    assert "reply 1" in html
    assert "<html" in html[:300]


def test_script_injection_is_escaped(tmp_path: Path) -> None:
    manager = _session_with(tmp_path, ["<script>alert('pwned')</script>"])

    html = render_session_html(export_session(manager))

    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html


def test_ansi_escapes_are_stripped(tmp_path: Path) -> None:
    manager = _session_with(tmp_path, ["\x1b[31mred\x1b[0m status"])

    html = render_session_html(export_session(manager))

    assert "\x1b" not in html
    assert "red status" in html


def test_custom_message_content_is_escaped(tmp_path: Path) -> None:
    manager = _session_with(
        tmp_path,
        ["plain"],
        custom=("official-status", '<img src=x onerror="alert(1)">'),
    )

    html = render_session_html(export_session(manager))

    assert "<img src=x" not in html
    assert "&lt;img src=x" in html


def test_exporter_port_writes_the_file(tmp_path: Path) -> None:
    manager = _session_with(tmp_path, ["persisted"])
    destination = tmp_path / "out" / "session.html"

    path = HtmlSessionExporter().export(export_session(manager), destination)

    assert path == destination
    content = destination.read_text(encoding="utf-8")
    assert "persisted" in content
    assert "<script>alert" not in content


def test_cli_export_writes_the_escaped_file(tmp_path: Path) -> None:
    from pi_ai import FakeProvider, fake_model
    from pi_coding_agent.cli.main import main
    from pi_coding_agent.model_runtime import ModelRuntime
    from pi_coding_agent.services import ServiceOverrides

    project = tmp_path / "project"
    project.mkdir()
    manager = _session_with(project, ["cli export proof"])
    assert manager.path is not None

    stdout = StringIO()
    stderr = StringIO()
    destination = tmp_path / "exported.html"
    code = main(
        ["--export", str(destination), "--session", str(manager.path)],
        stdout=stdout,
        stderr=stderr,
        cwd=project,
        environ={"PI_PYTHON_AGENT_DIR": str(tmp_path / "agent")},
        service_overrides=ServiceOverrides(exporter=HtmlSessionExporter()),
        model_runtime=ModelRuntime(provider=FakeProvider([]), model=fake_model()),
    )

    assert code == 0, stderr.getvalue()
    content = destination.read_text(encoding="utf-8")
    assert "cli export proof" in content
    assert stdout.getvalue().strip() != ""
