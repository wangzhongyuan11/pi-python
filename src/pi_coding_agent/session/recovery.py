"""Conservative recovery for Tool Calls whose execution state is unknowable."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from pi_ai import AssistantMessage, TextContent, ToolCall, ToolResultMessage
from pi_ai.wire.messages import dump_message

from .agent_messages import parse_message_entry
from .manager import SessionManager
from .models import MessageEntry

RECOVERY_MESSAGE = (
    "Tool execution state is unknown after session recovery; the tool was not replayed."
)


def _entry_id() -> str:
    return uuid4().hex


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _milliseconds(timestamp: str) -> int:
    normalized = timestamp[:-1] + "+00:00" if timestamp.endswith("Z") else timestamp
    return int(datetime.fromisoformat(normalized).timestamp() * 1000)


def recover_unmatched_tool_calls(
    manager: SessionManager,
    *,
    entry_id_factory: Callable[[], str] = _entry_id,
    timestamp_factory: Callable[[], str] = _timestamp,
) -> tuple[MessageEntry, ...]:
    calls: dict[str, ToolCall] = {}
    resolved: set[str] = set()
    for entry in manager.active_path():
        if not isinstance(entry, MessageEntry):
            continue
        message = parse_message_entry(entry)
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ToolCall):
                    calls.setdefault(block.id, block)
        elif isinstance(message, ToolResultMessage):
            resolved.add(message.tool_call_id)

    recovered: list[MessageEntry] = []
    for tool_call_id, call in calls.items():
        if tool_call_id in resolved:
            continue
        timestamp = timestamp_factory()
        entry = MessageEntry(
            type="message",
            id=entry_id_factory(),
            parent_id=manager.leaf_id,
            timestamp=timestamp,
            message=dump_message(
                ToolResultMessage(
                    tool_call_id=call.id,
                    tool_name=call.name,
                    content=(TextContent(text=RECOVERY_MESSAGE),),
                    is_error=True,
                    timestamp=_milliseconds(timestamp),
                )
            ),
        )
        manager.append(entry)
        recovered.append(entry)
    return tuple(recovered)


__all__ = ["RECOVERY_MESSAGE", "recover_unmatched_tool_calls"]
