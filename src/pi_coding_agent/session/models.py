"""Pydantic wire models for the mature Pi Session v3 JSONL format."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from pi_ai import JsonValue


class _SessionWireModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        validate_by_alias=True,
        validate_by_name=True,
        extra="allow",
        strict=True,
    )


class SessionHeader(_SessionWireModel):
    type: Literal["session"]
    version: Literal[3]
    id: str
    timestamp: str
    cwd: str
    parent_session: str | None = None


class SessionEntry(_SessionWireModel):
    id: str
    parent_id: str | None
    timestamp: str


class MessageEntry(SessionEntry):
    type: Literal["message"]
    message: dict[str, JsonValue]


class ThinkingLevelChangeEntry(SessionEntry):
    type: Literal["thinking_level_change"]
    thinking_level: str


class ModelChangeEntry(SessionEntry):
    type: Literal["model_change"]
    provider: str
    model_id: str


class CompactionEntry(SessionEntry):
    type: Literal["compaction"]
    summary: str
    first_kept_entry_id: str
    tokens_before: int
    details: JsonValue = None
    usage: dict[str, JsonValue] | None = None
    from_hook: bool | None = None


class BranchSummaryEntry(SessionEntry):
    type: Literal["branch_summary"]
    from_id: str
    summary: str
    details: JsonValue = None
    usage: dict[str, JsonValue] | None = None
    from_hook: bool | None = None


class CustomEntry(SessionEntry):
    type: Literal["custom"]
    custom_type: str
    data: JsonValue = None


class CustomMessageEntry(SessionEntry):
    type: Literal["custom_message"]
    custom_type: str
    content: str | list[dict[str, JsonValue]]
    display: bool
    details: JsonValue = None


class LabelEntry(SessionEntry):
    type: Literal["label"]
    target_id: str
    label: str | None = None


class SessionInfoEntry(SessionEntry):
    type: Literal["session_info"]
    name: str | None = None


type KnownSessionEntry = Annotated[
    MessageEntry
    | ThinkingLevelChangeEntry
    | ModelChangeEntry
    | CompactionEntry
    | BranchSummaryEntry
    | CustomEntry
    | CustomMessageEntry
    | LabelEntry
    | SessionInfoEntry,
    Field(discriminator="type"),
]

type SessionRecord = Annotated[SessionHeader | KnownSessionEntry, Field(discriminator="type")]


@dataclass(frozen=True, slots=True)
class ImportResult:
    session_id: str
    session_file: Path
    source_file: Path


__all__ = [
    "BranchSummaryEntry",
    "CompactionEntry",
    "CustomEntry",
    "CustomMessageEntry",
    "ImportResult",
    "KnownSessionEntry",
    "LabelEntry",
    "MessageEntry",
    "ModelChangeEntry",
    "SessionEntry",
    "SessionHeader",
    "SessionInfoEntry",
    "SessionRecord",
    "ThinkingLevelChangeEntry",
]
