"""Extension events for session replacement, compaction, and tree navigation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from ..compaction.cutpoint import CompactionCutPoint
from ..compaction.service import CompactionReason
from ..session.models import (
    BranchSummaryEntry,
    CompactionEntry,
    SessionEntry,
)

type SessionStartReason = Literal["startup", "reload", "new", "resume", "fork"]
type SessionShutdownReason = Literal["quit", "reload", "new", "resume", "fork"]


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionStartEvent:
    reason: SessionStartReason
    previous_session_file: str | None = None
    type: Literal["session_start"] = field(default="session_start", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionBeforeSwitchEvent:
    reason: Literal["new", "resume"]
    target_session_file: str | None = None
    type: Literal["session_before_switch"] = field(default="session_before_switch", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionBeforeForkEvent:
    entry_id: str | None
    position: Literal["before", "at"] = "at"
    type: Literal["session_before_fork"] = field(default="session_before_fork", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionShutdownEvent:
    reason: SessionShutdownReason
    target_session_file: str | None = None
    type: Literal["session_shutdown"] = field(default="session_shutdown", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionBeforeCompactEvent:
    preparation: CompactionCutPoint
    branch_entries: tuple[SessionEntry, ...]
    reason: CompactionReason
    will_retry: bool
    type: Literal["session_before_compact"] = field(default="session_before_compact", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionCompactEvent:
    compaction_entry: CompactionEntry
    from_extension: bool
    reason: CompactionReason
    will_retry: bool
    type: Literal["session_compact"] = field(default="session_compact", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class TreePreparation:
    target_id: str
    old_leaf_id: str | None
    common_ancestor_id: str | None
    entries_to_summarize: tuple[SessionEntry, ...]
    user_wants_summary: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionBeforeTreeEvent:
    preparation: TreePreparation
    type: Literal["session_before_tree"] = field(default="session_before_tree", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionTreeEvent:
    new_leaf_id: str | None
    old_leaf_id: str | None
    summary_entry: BranchSummaryEntry | None = None
    from_extension: bool = False
    type: Literal["session_tree"] = field(default="session_tree", init=False)


type ExtensionSessionEvent = (
    SessionStartEvent
    | SessionBeforeSwitchEvent
    | SessionBeforeForkEvent
    | SessionShutdownEvent
    | SessionBeforeCompactEvent
    | SessionCompactEvent
    | SessionBeforeTreeEvent
    | SessionTreeEvent
)


__all__ = [
    "ExtensionSessionEvent",
    "SessionBeforeCompactEvent",
    "SessionBeforeForkEvent",
    "SessionBeforeSwitchEvent",
    "SessionBeforeTreeEvent",
    "SessionCompactEvent",
    "SessionShutdownEvent",
    "SessionShutdownReason",
    "SessionStartEvent",
    "SessionStartReason",
    "SessionTreeEvent",
    "TreePreparation",
]
