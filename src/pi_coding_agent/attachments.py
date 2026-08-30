"""File and image attachment message contracts (no graphics protocols)."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import cast

from pi_ai import JsonValue, Model

_IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


class AttachmentError(ValueError):
    """An attachment is missing, unsupported, or exceeds its size limit."""


def supports_image_input(model: Model) -> bool:
    """Derive image support from the model's declared input capabilities."""

    return "image" in model.input


def classify_attachment(path: Path) -> str:
    """Classify an attachment candidate as ``image`` or ``text`` by suffix."""

    return "image" if path.suffix.lower() in _IMAGE_MIME_TYPES else "text"


def build_text_file_attachment(path: Path) -> dict[str, JsonValue]:
    try:
        if not path.is_file():
            raise AttachmentError(f"attachment file missing: {path}")
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
    try:
        if not path.is_file():
            raise AttachmentError(f"attachment file missing: {path}")
        size = path.stat().st_size
    except OSError as error:
        raise AttachmentError(f"cannot inspect image attachment: {path}") from error
    mime_type = _IMAGE_MIME_TYPES.get(path.suffix.lower())
    if mime_type is None:
        raise AttachmentError(f"unsupported image format: {path.suffix!r}")
    if size > max_bytes:
        raise AttachmentError(f"image exceeds size limit: {size} > {max_bytes}")
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise AttachmentError(f"cannot read image attachment: {path}") from error
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


__all__ = [
    "AttachmentError",
    "build_image_attachment",
    "build_text_file_attachment",
    "classify_attachment",
    "supports_image_input",
]
