"""P17-T01: @file and explicit CLI attachment arguments.

File arguments expand into the same text/image AgentMessage contract the TUI
uses; RPC mode rejects argv attachments outright; the print path delivers the
expanded content to the model.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest

from pi_ai import FakeProvider, ImageContent, fake_assistant_message
from pi_coding_agent.attachments import AttachmentError
from pi_coding_agent.cli.file_args import (
    process_file_arguments,
    split_file_arguments,
)
from pi_coding_agent.cli.main import main
from pi_coding_agent.model_runtime import ModelRuntime


def _runtime(provider: FakeProvider) -> ModelRuntime:
    return ModelRuntime(provider=provider, model=provider.models[0])


def test_split_extracts_at_prefixed_arguments_and_keeps_messages() -> None:
    messages, file_args = split_file_arguments(["explain", "@notes.md", "this", "@img.png"])

    assert messages == ["explain", "this"]
    assert file_args == ["notes.md", "img.png"]


def test_text_file_expands_into_the_file_envelope(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text("# Notes\n\nremember the contract", encoding="utf-8")

    files = process_file_arguments(
        ["notes.md"], cwd=tmp_path, image_supported=True, max_image_bytes=10 * 1024 * 1024
    )

    assert files.images == ()
    assert '<file name="' in files.text
    assert "notes.md" in files.text
    assert "# Notes\n\nremember the contract" in files.text


def test_image_file_becomes_an_image_content_with_a_reference(tmp_path: Path) -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"pixel" * 8
    (tmp_path / "shot.png").write_bytes(png)

    files = process_file_arguments(
        ["shot.png"], cwd=tmp_path, image_supported=True, max_image_bytes=10 * 1024 * 1024
    )

    assert len(files.images) == 1
    image = files.images[0]
    assert isinstance(image, ImageContent)
    assert image.mime_type == "image/png"
    assert image.data  # base64 payload present
    assert "shot.png" in files.text


def test_missing_file_is_a_typed_error(tmp_path: Path) -> None:
    with pytest.raises(AttachmentError, match="File not found"):
        process_file_arguments(
            ["missing.md"],
            cwd=tmp_path,
            image_supported=True,
            max_image_bytes=10 * 1024 * 1024,
        )


def test_empty_file_is_skipped(tmp_path: Path) -> None:
    (tmp_path / "empty.txt").write_text("", encoding="utf-8")

    files = process_file_arguments(
        ["empty.txt"], cwd=tmp_path, image_supported=True, max_image_bytes=10 * 1024 * 1024
    )

    assert files.text == ""
    assert files.images == ()


def test_image_on_a_text_only_model_is_a_capability_error(tmp_path: Path) -> None:
    (tmp_path / "shot.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"pixel" * 8)

    with pytest.raises(AttachmentError, match="does not support image input"):
        process_file_arguments(
            ["shot.png"], cwd=tmp_path, image_supported=False, max_image_bytes=10 * 1024 * 1024
        )


def test_oversized_image_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "big.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"pixel" * 8)

    with pytest.raises(AttachmentError, match="exceeds size limit"):
        process_file_arguments(["big.png"], cwd=tmp_path, image_supported=True, max_image_bytes=8)


def test_rpc_mode_rejects_file_arguments(tmp_path: Path) -> None:
    stdout = StringIO()
    stderr = StringIO()

    code = main(
        ["--mode", "rpc", "--no-session", "@notes.md"],
        stdin=StringIO(),
        stdout=stdout,
        stderr=stderr,
        cwd=tmp_path,
        environ={"PI_PYTHON_AGENT_DIR": str(tmp_path / "agent")},
        model_runtime=_runtime(FakeProvider([])),
    )

    assert code == 1
    assert "@file arguments are not supported in RPC mode" in stderr.getvalue()
    assert stdout.getvalue() == ""


def test_print_mode_delivers_expanded_file_content_to_the_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "notes.md").write_text("the deployment key is honeybadger", encoding="utf-8")
    monkeypatch.setenv("PI_PYTHON_AGENT_DIR", str(tmp_path / "agent"))
    provider = FakeProvider([fake_assistant_message("noted")])

    stdout = StringIO()
    stderr = StringIO()
    code = main(
        ["-p", "summarize", "@notes.md", "--no-session"],
        stdout=stdout,
        stderr=stderr,
        cwd=project,
        environ={"PI_PYTHON_AGENT_DIR": str(tmp_path / "agent")},
        model_runtime=_runtime(provider),
    )

    assert code == 0, stderr.getvalue()
    request_messages = provider.calls[0][1].messages
    user = request_messages[0]
    text_blocks = [block.text for block in user.content if getattr(block, "type", "") == "text"]
    assert "summarize" in text_blocks[0]
    assert any("the deployment key is honeybadger" in text for text in text_blocks)
    assert any("<file name=" in text for text in text_blocks)
