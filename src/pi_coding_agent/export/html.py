"""Escape-first HTML session export (P17-T03).

Every dynamic fragment is HTML-escaped and ANSI escapes are stripped before
rendering, so model output, tool results, and extension messages can never
inject markup or scripts into the exported document.
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import cast

from ..ports import SessionExporter
from ..session.export import SessionTranscript, export_session
from ..session.manager import SessionManager

_ANSI_ESCAPE = re.compile(r"\x1b(?:\[[0-9;?]*[A-Za-z]|\][^\x07]*(?:\x07|\x1b\\)|[P^_].*?\x1b\\)")

_MESSAGE_ROLE_LABELS = {"user": "user", "assistant": "assistant", "toolResult": "tool result"}


def sanitize_text(value: object) -> str:
    """Strip ANSI escapes and HTML-escape a dynamic text fragment."""

    plain = _ANSI_ESCAPE.sub("", str(value))
    return html.escape(plain, quote=True)


def render_session_html(transcript: SessionTranscript) -> str:
    """Render one session branch as a standalone, self-contained document."""

    rows: list[str] = []
    for entry in transcript.entries:
        message = getattr(entry, "message", None)
        if message is None:
            custom_type = getattr(entry, "custom_type", None)
            if isinstance(custom_type, str):
                label = sanitize_text(f"custom · {custom_type}")
                content = sanitize_text(getattr(entry, "content", ""))
                rows.append(
                    f'<section class="entry custom"><h2>{label}</h2><pre>{content}</pre></section>'
                )
            continue
        role = str(message.get("role", ""))
        label = _MESSAGE_ROLE_LABELS.get(role, sanitize_text(role))
        body = sanitize_text(_message_text(message))
        rows.append(
            f'<section class="entry {sanitize_text(role)}"><h2>{label}</h2>'
            f"<pre>{body}</pre></section>"
        )

    title = sanitize_text(f"Session {transcript.session_id}")
    session_meta = sanitize_text(f"{transcript.header.timestamp} · leaf {transcript.leaf_id[:8]}")
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        f"<title>{title}</title>\n"
        "<style>\n"
        "body{font-family:system-ui,sans-serif;margin:2rem auto;max-width:60rem;}"
        "section.entry{border:1px solid #ddd;border-radius:6px;padding:0.5rem 1rem;"
        "margin-bottom:0.75rem;}"
        "section.entry h2{font-size:0.85rem;margin:0 0 0.4rem;color:#555;"
        "text-transform:uppercase;}"
        "pre{white-space:pre-wrap;word-break:break-word;margin:0;font-family:inherit;}\n"
        "</style>\n</head>\n<body>\n"
        f"<h1>{title}</h1>\n<p>{session_meta}</p>\n" + "\n".join(rows) + "\n</body>\n</html>\n"
    )


def _message_text(message: object) -> str:
    mapping = cast("dict[str, object]", message)
    content = mapping.get("content")
    if isinstance(content, str):
        return content
    parts: list[str] = []
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            kind = str(block.get("type", ""))
            if kind == "text":
                parts.append(str(block.get("text", "")))
            elif kind == "image":
                parts.append(f"[image {block.get('mimeType', 'unknown')}]")
            elif kind == "toolCall":
                parts.append(f"[tool call {block.get('name', '')} {block.get('arguments', {})}]")
    if mapping.get("role") == "toolResult":
        parts.append(f"[tool {mapping.get('toolName', '')}]")
    return "\n".join(parts)


class HtmlSessionExporter(SessionExporter):
    """SessionExporter port implementation writing escaped HTML documents."""

    def export(self, transcript: object, destination: Path) -> Path:
        projected = cast("SessionTranscript", transcript)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(render_session_html(projected), encoding="utf-8")
        return destination


def export_session_html(
    source: str | Path | SessionManager, destination: Path, *, leaf_id: str | None = None
) -> Path:
    """Project one session branch and write its escaped HTML document."""

    return HtmlSessionExporter().export(export_session(source, leaf_id=leaf_id), destination)


__all__ = [
    "HtmlSessionExporter",
    "export_session_html",
    "render_session_html",
    "sanitize_text",
]
