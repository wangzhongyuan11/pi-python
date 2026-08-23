"""Immutable indexes over an append-only Session entry tree."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .errors import SessionGraphError
from .models import SessionEntry


@dataclass(frozen=True, slots=True)
class SessionTree:
    entries: tuple[SessionEntry, ...]
    by_id: Mapping[str, SessionEntry]
    child_ids: Mapping[str, tuple[str, ...]]
    root_id: str | None
    leaf_ids: tuple[str, ...]

    @classmethod
    def build(cls, entries: tuple[SessionEntry, ...]) -> SessionTree:
        by_id: dict[str, SessionEntry] = {}
        children: dict[str, list[str]] = {}
        root_id: str | None = None
        for entry in entries:
            if entry.id in by_id:
                raise SessionGraphError(f"duplicate entry id: {entry.id}")
            if entry.parent_id is None:
                if root_id is not None:
                    raise SessionGraphError("session tree has more than one root")
                root_id = entry.id
            elif entry.parent_id not in by_id:
                raise SessionGraphError(
                    f"parent {entry.parent_id!r} must reference an earlier entry"
                )
            by_id[entry.id] = entry
            children.setdefault(entry.id, [])
            if entry.parent_id is not None:
                children.setdefault(entry.parent_id, []).append(entry.id)
        child_ids = {key: tuple(value) for key, value in children.items()}
        leaves = tuple(entry.id for entry in entries if not child_ids[entry.id])
        return cls(
            entries=entries,
            by_id=MappingProxyType(by_id),
            child_ids=MappingProxyType(child_ids),
            root_id=root_id,
            leaf_ids=leaves,
        )

    def children_of(self, entry_id: str) -> tuple[SessionEntry, ...]:
        self._require(entry_id)
        return tuple(self.by_id[child_id] for child_id in self.child_ids[entry_id])

    def active_path(self, leaf_id: str) -> tuple[SessionEntry, ...]:
        current = self._require(leaf_id)
        reversed_path: list[SessionEntry] = []
        while True:
            reversed_path.append(current)
            if current.parent_id is None:
                break
            current = self.by_id[current.parent_id]
        reversed_path.reverse()
        return tuple(reversed_path)

    def _require(self, entry_id: str) -> SessionEntry:
        try:
            return self.by_id[entry_id]
        except KeyError as error:
            raise SessionGraphError(f"unknown entry: {entry_id}") from error


__all__ = ["SessionTree"]
