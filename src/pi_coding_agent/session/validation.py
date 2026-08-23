"""Shared semantic validation for parsed and newly appended Session entries."""

from __future__ import annotations

from datetime import datetime
from typing import Never

from pydantic import ValidationError

from pi_agent import AgentMessage
from pi_ai import AssistantMessage, ToolCall, ToolResultMessage

from .agent_messages import parse_message_entry
from .errors import EntryValidationError, SessionGraphError
from .models import CompactionEntry, MessageEntry, SessionEntry


class SessionEntryValidator:
    """Incrementally validate one append-only Session tree."""

    def __init__(self) -> None:
        self._by_id: dict[str, SessionEntry] = {}
        self._messages: dict[str, AgentMessage] = {}
        self._root_id: str | None = None

    def validate_next(self, entry: SessionEntry) -> AgentMessage | None:
        index = len(self._by_id)
        self._validate_timestamp(index, entry.timestamp)
        if entry.id in self._by_id:
            self._fail(index, f"duplicate entry id: {entry.id}")
        if entry.parent_id is None:
            if self._root_id is not None:
                self._fail(index, "session has more than one root")
        elif entry.parent_id not in self._by_id:
            self._fail(index, "parentId must reference an earlier entry")
        if isinstance(entry, CompactionEntry):
            if entry.first_kept_entry_id not in self._ancestors(entry):
                self._fail(index, "compaction firstKeptEntryId is not an ancestor")
        if not isinstance(entry, MessageEntry):
            return None
        try:
            message = parse_message_entry(entry)
        except (KeyError, SessionGraphError, TypeError, ValidationError, ValueError):
            self._fail(index, "invalid AgentMessage")
        if isinstance(message, ToolResultMessage):
            self._validate_tool_result(index, entry, message)
        return message

    def accept(self, entry: SessionEntry, message: AgentMessage | None) -> None:
        if entry.parent_id is None:
            self._root_id = entry.id
        self._by_id[entry.id] = entry
        if message is not None:
            self._messages[entry.id] = message

    def _ancestors(self, entry: SessionEntry) -> tuple[str, ...]:
        result: list[str] = []
        current = entry.parent_id
        while current is not None:
            result.append(current)
            current = self._by_id[current].parent_id
        return tuple(result)

    def _validate_tool_result(
        self,
        index: int,
        entry: MessageEntry,
        message: ToolResultMessage,
    ) -> None:
        matched_call: ToolCall | None = None
        for ancestor_id in self._ancestors(entry):
            ancestor_message = self._messages.get(ancestor_id)
            if (
                isinstance(ancestor_message, ToolResultMessage)
                and ancestor_message.tool_call_id == message.tool_call_id
            ):
                self._fail(index, "duplicate tool result on active branch")
            if isinstance(ancestor_message, AssistantMessage):
                matched_call = next(
                    (
                        item
                        for item in ancestor_message.content
                        if isinstance(item, ToolCall) and item.id == message.tool_call_id
                    ),
                    matched_call,
                )
        if matched_call is None or matched_call.name != message.tool_name:
            self._fail(index, "tool result has no matching ancestor tool call")

    @staticmethod
    def _validate_timestamp(index: int, value: str) -> None:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            datetime.fromisoformat(normalized)
        except ValueError:
            SessionEntryValidator._fail(index, "timestamp is not ISO-8601")

    @staticmethod
    def _fail(index: int, reason: str) -> Never:
        raise EntryValidationError(index, reason)


def validate_session_entries(entries: tuple[SessionEntry, ...]) -> None:
    """Reject every sequence that cannot be safely persisted or resumed."""

    validator = SessionEntryValidator()
    for entry in entries:
        message = validator.validate_next(entry)
        validator.accept(entry, message)


__all__ = ["SessionEntryValidator", "validate_session_entries"]
