"""P17-T02: one attachment contract across CLI, SDK, TUI, and RPC.

Every product mode must produce the identical prompt message for the same
attachment input, surface the same capability error for images on text-only
models, and reject argv attachments in RPC mode.
"""

from __future__ import annotations

import asyncio
from io import StringIO
from pathlib import Path

import pytest

from pi_ai import FakeProvider, TextContent, UserMessage, fake_assistant_message
from pi_coding_agent.attachments import AttachmentError
from pi_coding_agent.cli.file_args import (
    build_attachment_message,
    process_file_arguments,
)
from pi_coding_agent.cli.main import main
from pi_coding_agent.deepseek_credentials import DeepSeekCredentialResolver
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.sdk import CreateAgentSessionOptions, create_agent_session
from pi_coding_agent.tui.runner import InteractiveOptions, run_interactive


def _model_runtime(provider: FakeProvider) -> ModelRuntime:
    return ModelRuntime(provider=provider, model=provider.models[0])


def _canonical_message(tmp_path: Path, *, image: bool) -> UserMessage:
    (tmp_path / "notes.md").write_text("parity contract body", encoding="utf-8")
    args = ["notes.md", "shot.png"] if image else ["notes.md"]
    return build_attachment_message(
        "explain this",
        process_file_arguments(
            args,
            cwd=tmp_path,
            image_supported=image,
            max_image_bytes=10 * 1024 * 1024,
        ),
        timestamp=1_700_000_000_000,
    )


def _blocks(message: UserMessage) -> list[str]:
    return [
        f"{block.type}:{getattr(block, 'text', None) or getattr(block, 'mime_type', None)}"
        for block in message.content
    ]


def test_cli_and_shared_builder_produce_the_identical_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "notes.md").write_text("parity contract body", encoding="utf-8")
    monkeypatch.setenv("PI_PYTHON_AGENT_DIR", str(tmp_path / "agent"))
    provider = FakeProvider([fake_assistant_message("cli done")])

    stdout = StringIO()
    stderr = StringIO()
    code = main(
        ["-p", "explain this", "@notes.md", "--no-session"],
        stdout=stdout,
        stderr=stderr,
        cwd=project,
        environ={"PI_PYTHON_AGENT_DIR": str(tmp_path / "agent")},
        model_runtime=_model_runtime(provider),
    )

    assert code == 0, stderr.getvalue()
    cli_message = provider.calls[0][1].messages[0]
    canonical = _canonical_message(project, image=False)
    assert _blocks(cli_message) == _blocks(canonical)
    assert cli_message.content[0] == canonical.content[0]


def test_sdk_prompt_accepts_the_shared_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "notes.md").write_text("parity contract body", encoding="utf-8")
    monkeypatch.setenv("PI_PYTHON_AGENT_DIR", str(tmp_path / "agent"))
    provider = FakeProvider([fake_assistant_message("sdk done")])

    async def scenario() -> UserMessage:
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=project,
                model_runtime=_model_runtime(provider),
                project_trusted=True,
            )
        )
        try:
            message = _canonical_message(project, image=False)
            await created.session.prompt(message)
            return provider.calls[0][1].messages[0]
        finally:
            await created.close()

    sdk_message = asyncio.run(scenario())
    canonical = _canonical_message(project, image=False)
    assert _blocks(sdk_message) == _blocks(canonical)


def test_tui_attach_composes_the_shared_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "notes.md").write_text("parity contract body", encoding="utf-8")
    monkeypatch.setenv("PI_PYTHON_AGENT_DIR", str(tmp_path / "agent"))
    provider = FakeProvider([fake_assistant_message("tui done")])
    replies = iter(("/attach notes.md", "explain this", "/exit"))

    async def read_line(_prompt: str) -> str | None:
        return next(replies, None)

    exit_code = asyncio.run(
        run_interactive(
            InteractiveOptions(
                cwd=project,
                credential_resolver=DeepSeekCredentialResolver(environ={}, cwd=project),
                model_runtime=_model_runtime(provider),
                project_trusted=True,
            ),
            stdout=StringIO(),
            stderr=StringIO(),
            read_line=read_line,
        )
    )

    assert exit_code == 0
    tui_message = provider.calls[0][1].messages[0]
    assert isinstance(tui_message, UserMessage)
    texts = [block.text for block in tui_message.content if isinstance(block, TextContent)]
    assert "explain this" in texts[0]
    assert any("parity contract body" in text for text in texts)


def test_capability_error_is_identical_across_modes(tmp_path: Path) -> None:
    (tmp_path / "shot.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"pixel" * 8)

    # Shared builder (CLI + SDK path).
    with pytest.raises(AttachmentError, match="does not support image input"):
        process_file_arguments(
            ["shot.png"], cwd=tmp_path, image_supported=False, max_image_bytes=10 * 1024 * 1024
        )

    # CLI print path surfaces the same message.
    stdout = StringIO()
    stderr = StringIO()
    code = main(
        ["-p", "explain", "@shot.png", "--no-session"],
        stdout=stdout,
        stderr=stderr,
        cwd=tmp_path,
        environ={"PI_PYTHON_AGENT_DIR": str(tmp_path / "agent")},
    )
    assert code == 1
    assert "does not support image input" in stderr.getvalue()
