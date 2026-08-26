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


def build_text_file_attachment(path: Path) -> dict[str, JsonValue]:
    if not path.is_file():
        raise AttachmentError(f"attachment file missing: {path}")
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise AttachmentError(f"cannot read text attachment: {path}") from error
    return cast(
        "dict[str, JsonValue]",
        {"type": "text", "name": path.name, "content": content},
    )


def build_image_attachment(
    path: Path, *, max_bytes: int, image_supported: bool = True
) -> dict[str, JsonValue]:
    if not image_supported:
        raise AttachmentError("selected model does not support image input")
    if max_bytes < 0:
        raise AttachmentError("image size limit must be non-negative")
    if not path.is_file():
        raise AttachmentError(f"attachment file missing: {path}")
    mime_type = _IMAGE_MIME_TYPES.get(path.suffix.lower())
    if mime_type is None:
        raise AttachmentError(f"unsupported image format: {path.suffix!r}")
    size = path.stat().st_size
    if size > max_bytes:
        raise AttachmentError(f"image exceeds size limit: {size} > {max_bytes}")
    payload = path.read_bytes()
    if len(payload) > max_bytes:
        raise AttachmentError(f"image exceeds size limit: {len(payload)} > {max_bytes}")
    return cast(
        "dict[str, JsonValue]",
        {
            "type": "image",
            "name": path.name,
            "mimeType": mime_type,
            "data": base64.b64encode(payload).decode("ascii"),
        },
    )


__all__ = ["AttachmentError", "build_image_attachment", "build_text_file_attachment"]
