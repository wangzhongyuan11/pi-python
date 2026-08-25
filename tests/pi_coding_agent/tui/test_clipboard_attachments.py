from __future__ import annotations

import base64
from pathlib import Path

import pytest

from pi_coding_agent.attachments import (
    AttachmentError,
    build_image_attachment,
    build_text_file_attachment,
)


def test_text_file_attachment_embeds_name_and_content(tmp_path: Path) -> None:
    source = tmp_path / "notes.txt"
    source.write_text("hello world", encoding="utf-8")

    attachment = build_text_file_attachment(source, source.read_text(encoding="utf-8"))

    assert attachment["type"] == "text"
    assert attachment["name"] == str(source)
    assert attachment["content"] == "hello world"


def test_image_attachment_requires_supported_format_and_size(tmp_path: Path) -> None:
    payload = b"\x89PNG fake"
    image = tmp_path / "shot.png"
    image.write_bytes(payload)

    attachment = build_image_attachment(image, max_bytes=1024)

    assert attachment["type"] == "image"
    assert base64.b64decode(str(attachment["data"])) == payload
    assert attachment["mimeType"] == "image/png"

    big = tmp_path / "big.png"
    big.write_bytes(b"x" * 2048)
    with pytest.raises(AttachmentError):
        build_image_attachment(big, max_bytes=1024)

    unsupported = tmp_path / "logo.bmp"
    unsupported.write_bytes(b"bm")
    with pytest.raises(AttachmentError):
        build_image_attachment(unsupported, max_bytes=1024)


def test_missing_files_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(AttachmentError):
        build_text_file_attachment(tmp_path / "missing.txt", "")
