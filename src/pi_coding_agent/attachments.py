"""File and image attachment message contracts (no graphics protocols)."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import cast

from pi_ai import JsonValue

_IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


class AttachmentError(ValueError):
    """An attachment is missing, unsupported, or exceeds its size limit."""


def build_text_file_attachment(path: Path, content: str) -> dict[str, JsonValue]:
    if not path.is_file():
        raise AttachmentError(f"attachment file missing: {path}")
    return cast(
        "dict[str, JsonValue]",
        {"type": "text", "name": str(path), "content": content},
    )


def build_image_attachment(path: Path, *, max_bytes: int) -> dict[str, JsonValue]:
    if not path.is_file():
        raise AttachmentError(f"attachment file missing: {path}")
    mime_type = _IMAGE_MIME_TYPES.get(path.suffix.lower())
    if mime_type is None:
        raise AttachmentError(f"unsupported image format: {path.suffix!r}")
    payload = path.read_bytes()
    if len(payload) > max_bytes:
        raise AttachmentError(f"image exceeds size limit: {len(payload)} > {max_bytes}")
    return cast(
        "dict[str, JsonValue]",
        {
            "type": "image",
            "name": str(path),
            "mimeType": mime_type,
            "data": base64.b64encode(payload).decode("ascii"),
        },
    )


__all__ = ["AttachmentError", "build_image_attachment", "build_text_file_attachment"]
