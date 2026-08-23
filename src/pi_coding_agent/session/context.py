"""Pure projection from one active Session path into Agent runtime context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import cast

from pi_agent import (
    AgentMessage,
    BranchSummaryMessage,
    CompactionSummaryMessage,
    CustomMessage,
)
from pi_ai import ImageContent, JsonValue, TextContent

from .agent_messages import parse_message_entry
from .errors import SessionGraphError
from .models import (
    BranchSummaryEntry,
    CompactionEntry,
    CustomMessageEntry,
    MessageEntry,
    ModelChangeEntry,
    SessionEntry,
    ThinkingLevelChangeEntry,
)
from .tree import SessionTree


@dataclass(frozen=True, slots=True)
class ModelSelection:
    provider: str
    model_id: str


@dataclass(frozen=True, slots=True)
class SessionContext:
    messages: tuple[AgentMessage, ...]
    thinking_level: str
    model: ModelSelection | None


def _timestamp(value: str) -> int:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return int(datetime.fromisoformat(normalized).timestamp() * 1000)
    except ValueError as error:
        raise SessionGraphError(f"invalid entry timestamp: {value}") from error


def _custom_content(
    value: str | list[dict[str, JsonValue]],
) -> str | tuple[TextContent | ImageContent, ...]:
    if isinstance(value, str):
        return value
    result: list[TextContent | ImageContent] = []
    for item in value:
        kind = item.get("type")
        if kind == "text" and isinstance(item.get("text"), str):
            result.append(TextContent(text=cast("str", item["text"])))
        elif (
            kind == "image"
            and isinstance(item.get("data"), str)
            and isinstance(item.get("mimeType"), str)
        ):
            result.append(
                ImageContent(
                    data=cast("str", item["data"]),
                    mime_type=cast("str", item["mimeType"]),
                )
            )
        else:
            raise SessionGraphError("custom message contains invalid content")
    return tuple(result)


def _context_entries(path: tuple[SessionEntry, ...]) -> tuple[SessionEntry, ...]:
    compact_index: int | None = None
    for index, entry in enumerate(path):
        if isinstance(entry, CompactionEntry):
            compact_index = index
    if compact_index is None:
        return path
    compaction = cast("CompactionEntry", path[compact_index])
    prefix = path[:compact_index]
    kept_index = next(
        (index for index, entry in enumerate(prefix) if entry.id == compaction.first_kept_entry_id),
        None,
    )
    if kept_index is None:
        raise SessionGraphError(
            f"compaction {compaction.id} references an invalid firstKeptEntryId"
        )
    return (compaction, *prefix[kept_index:], *path[compact_index + 1 :])


def _entry_messages(entry: SessionEntry) -> tuple[AgentMessage, ...]:
    if isinstance(entry, MessageEntry):
        return (parse_message_entry(entry),)
    if isinstance(entry, CustomMessageEntry):
        return (
            CustomMessage(
                custom_type=entry.custom_type,
                content=_custom_content(entry.content),
                display=entry.display,
                details=entry.details,
                timestamp=_timestamp(entry.timestamp),
            ),
        )
    if isinstance(entry, BranchSummaryEntry) and entry.summary:
        return (
            BranchSummaryMessage(
                summary=entry.summary,
                from_id=entry.from_id,
                timestamp=_timestamp(entry.timestamp),
            ),
        )
    if isinstance(entry, CompactionEntry):
        return (
            CompactionSummaryMessage(
                summary=entry.summary,
                tokens_before=entry.tokens_before,
                timestamp=_timestamp(entry.timestamp),
            ),
        )
    return ()


def project_session_context(tree: SessionTree, leaf_id: str) -> SessionContext:
    path = tree.active_path(leaf_id)
    thinking_level = "off"
    model: ModelSelection | None = None
    for entry in path:
        if isinstance(entry, ThinkingLevelChangeEntry):
            thinking_level = entry.thinking_level
        elif isinstance(entry, ModelChangeEntry):
            model = ModelSelection(provider=entry.provider, model_id=entry.model_id)
        elif isinstance(entry, MessageEntry) and entry.message.get("role") == "assistant":
            provider = entry.message.get("provider")
            model_id = entry.message.get("model")
            if isinstance(provider, str) and isinstance(model_id, str):
                model = ModelSelection(provider=provider, model_id=model_id)
    messages = tuple(
        message for entry in _context_entries(path) for message in _entry_messages(entry)
    )
    return SessionContext(messages=messages, thinking_level=thinking_level, model=model)


__all__ = ["ModelSelection", "SessionContext", "project_session_context"]
