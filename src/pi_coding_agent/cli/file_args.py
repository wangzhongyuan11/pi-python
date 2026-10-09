"""Process @file and explicit CLI attachment arguments (P17-T01).

Mirrors the upstream ``cli/file-processor.ts`` contract: file arguments
expand into ``<file>`` text envelopes plus image attachments; missing files
and unsupported images are typed errors; empty files are skipped. The message
assembly itself lives in the shared attachment builder so every product mode
produces identical messages.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from pi_ai import ImageContent, TextContent, UserMessage

from ..attachments import (
    AttachmentError,
    build_image_attachment,
    build_text_file_attachment,
    classify_attachment,
)

_MAX_IMAGE_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ProcessedFiles:
    """Expanded file arguments: envelope text plus image attachments."""

    text: str
    images: tuple[ImageContent, ...]


def split_file_arguments(arguments: Sequence[str]) -> tuple[list[str], list[str]]:
    """Split positionals into prompt messages and ``@``-prefixed file args."""

    messages: list[str] = []
    file_args: list[str] = []
    for argument in arguments:
        if argument.startswith("@"):
            file_args.append(argument[1:])
        else:
            messages.append(argument)
    return messages, file_args


def process_file_arguments(
    file_args: Sequence[str],
    *,
    cwd: Path,
    image_supported: bool,
    max_image_bytes: int = _MAX_IMAGE_BYTES,
) -> ProcessedFiles:
    """Expand file arguments into envelope text and image attachments."""

    text_parts: list[str] = []
    images: list[ImageContent] = []
    for file_arg in file_args:
        path = Path(file_arg)
        if not path.is_absolute():
            path = cwd / path
        path = path.resolve()
        if not path.is_file():
            raise AttachmentError(f"File not found: {path}")
        if path.stat().st_size == 0:
            continue
        if classify_attachment(path) == "image":
            attachment = build_image_attachment(
                path, max_bytes=max_image_bytes, image_supported=image_supported
            )
            images.append(
                ImageContent(
                    data=str(attachment["data"]),
                    mime_type=str(attachment["mimeType"]),
                )
            )
            text_parts.append(f'<file name="{path}"></file>')
            continue
        attachment = build_text_file_attachment(path)
        content = cast("str", attachment["content"])
        text_parts.append(f'<file name="{path}">\n{content}\n</file>')
    return ProcessedFiles(text="".join(text_parts), images=tuple(images))


def build_attachment_message(
    prompt: str,
    files: ProcessedFiles,
    *,
    timestamp: int,
) -> UserMessage:
    """Assemble the shared text/image prompt message (P17-T02).

    Every product mode (CLI print, SDK, TUI initial message) must produce the
    identical message shape for the same inputs: the prompt text first, then
    the expanded file envelopes, then the image attachments.
    """

    blocks: list[TextContent | ImageContent] = [TextContent(text=prompt)]
    if files.text:
        blocks.append(TextContent(text=files.text))
    blocks.extend(files.images)
    return UserMessage(content=tuple(blocks), timestamp=timestamp)


__all__ = [
    "ProcessedFiles",
    "build_attachment_message",
    "process_file_arguments",
    "split_file_arguments",
]
