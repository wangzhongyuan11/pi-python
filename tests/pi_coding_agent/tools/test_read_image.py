"""Image reading support in the read tool (P11.5-T08)."""

from __future__ import annotations

import asyncio
import base64
import struct
import zlib
from pathlib import Path

from pi_ai import ImageContent, TextContent
from pi_coding_agent.tools.read import read_file
from pi_coding_agent.tools.registry import create_all_tools


def _png_bytes(width: int = 8, height: int = 8) -> bytes:
    def chunk(tag: bytes, payload: bytes) -> bytes:
        raw = tag + payload
        return struct.pack(">I", len(payload)) + raw + struct.pack(">I", zlib.crc32(raw))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = b"\x00" + b"\x10\x20\x30" * width
    body = zlib.compress(row * height)
    return (
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", body) + chunk(b"IEND", b"")
    )


class TestImageDetection:
    def test_png_file_returns_base64_image_payload(self, tmp_path: Path) -> None:
        target = tmp_path / "logo.png"
        raw = _png_bytes()
        target.write_bytes(raw)
        result = asyncio.run(read_file(target, cwd=tmp_path))
        assert result.image_mime == "image/png"
        assert base64.b64decode(result.image_data or "") == raw
        assert result.text.startswith("Read image file [image/png]")

    def test_jpeg_magic_bytes_are_detected(self, tmp_path: Path) -> None:
        target = tmp_path / "photo.jpg"
        target.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 32)
        result = asyncio.run(read_file(target, cwd=tmp_path))
        assert result.image_mime == "image/jpeg"

    def test_webp_magic_bytes_are_detected(self, tmp_path: Path) -> None:
        target = tmp_path / "pic.webp"
        target.write_bytes(b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 16)
        result = asyncio.run(read_file(target, cwd=tmp_path))
        assert result.image_mime == "image/webp"

    def test_bmp_is_detected_but_omitted_inline(self, tmp_path: Path) -> None:
        target = tmp_path / "legacy.bmp"
        target.write_bytes(b"BM" + b"\x00" * 32)
        result = asyncio.run(read_file(target, cwd=tmp_path))
        assert result.image_mime is None
        assert "Read image file [image/bmp]" in result.text
        assert "omitted" in result.text

    def test_text_file_is_not_detected_as_image(self, tmp_path: Path) -> None:
        target = tmp_path / "notes.txt"
        target.write_text("plain text", encoding="utf-8")
        result = asyncio.run(read_file(target, cwd=tmp_path))
        assert result.image_mime is None
        assert result.image_data is None


class TestRegistryImageContent:
    def test_read_tool_emits_text_and_image_blocks(self, tmp_path: Path) -> None:
        raw = _png_bytes()
        (tmp_path / "logo.png").write_bytes(raw)
        (read_tool,) = create_all_tools(cwd=tmp_path, tool_names=("read",))
        params = read_tool.validate_arguments({"path": "logo.png"})
        result = asyncio.run(read_tool.execute("call-read", params))
        assert isinstance(result.content[0], TextContent)
        image = result.content[1]
        assert isinstance(image, ImageContent)
        assert image.mime_type == "image/png"
        assert base64.b64decode(image.data) == raw
        details = result.details
        assert isinstance(details, dict)
        assert details["imageMime"] == "image/png"
