"""Replay one active session path into restored runtime state."""

from __future__ import annotations

from dataclasses import dataclass

from .context import ModelSelection
from .models import (
    CompactionEntry,
    MessageEntry,
    ModelChangeEntry,
    SessionEntry,
    ThinkingLevelChangeEntry,
)
from .tree import SessionTree


@dataclass(frozen=True, slots=True)
class RestoredState:
    thinking_level: str
    model: ModelSelection | None
    compaction: CompactionEntry | None


def restore_session_state(tree: SessionTree, leaf_id: str) -> RestoredState:
    thinking_level = "off"
    model: ModelSelection | None = None
    compaction: CompactionEntry | None = None
    path: tuple[SessionEntry, ...] = tree.active_path(leaf_id)
    for entry in path:
        if isinstance(entry, ThinkingLevelChangeEntry):
            thinking_level = entry.thinking_level
            continue
        if isinstance(entry, ModelChangeEntry):
            model = ModelSelection(provider=entry.provider, model_id=entry.model_id)
            continue
        if isinstance(entry, MessageEntry) and entry.message.get("role") == "assistant":
            provider = entry.message.get("provider")
            model_id = entry.message.get("model")
            if isinstance(provider, str) and isinstance(model_id, str):
                model = ModelSelection(provider=provider, model_id=model_id)
            continue
        if isinstance(entry, CompactionEntry):
            compaction = entry
    return RestoredState(thinking_level=thinking_level, model=model, compaction=compaction)


__all__ = ["RestoredState", "restore_session_state"]
