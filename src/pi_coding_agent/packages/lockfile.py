"""Atomic lockfile for installed extension packages."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast


class LockfileError(RuntimeError):
    """Base error for lockfile load/save problems."""


class LockfileWriteError(LockfileError):
    """The lockfile could not be written atomically."""


@dataclass(frozen=True, slots=True)
class LockEntry:
    name: str
    spec: str
    location: str
    version: str | None = None
    commit: str | None = None
    content_hash: str | None = None


def load_entries(path: Path) -> tuple[LockEntry, ...]:
    if not path.exists():
        return ()
    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LockfileError(f"corrupt lockfile: {path}") from error
    if not isinstance(payload, list):
        raise LockfileError(f"lockfile must contain a list: {path}")
    entries: list[LockEntry] = []
    for raw_item in cast("list[object]", payload):
        if not isinstance(raw_item, dict):
            raise LockfileError(f"lockfile entry must be an object: {path}")
        item = cast("dict[str, object]", raw_item)
        entries.append(
            LockEntry(
                name=str(item["name"]),
                spec=str(item["spec"]),
                location=str(item["location"]),
                version=cast("str | None", item.get("version")),
                commit=cast("str | None", item.get("commit")),
                content_hash=cast("str | None", item.get("content_hash")),
            )
        )
    return tuple(entries)


def save_entries(path: Path, entries: Sequence[LockEntry]) -> None:
    directory = path.parent
    try:
        directory.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=directory,
            prefix=path.name + ".",
            suffix=".tmp",
            delete=False,
        )
        with handle:
            json.dump([asdict(entry) for entry in entries], handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, path)
    except OSError as error:
        raise LockfileWriteError(f"cannot write lockfile {path}: {error}") from error


def replace_entry(entries: Sequence[LockEntry], entry: LockEntry) -> tuple[LockEntry, ...]:
    kept = [item for item in entries if item.name != entry.name]
    return (*kept, entry)


__all__ = [
    "LockEntry",
    "LockfileError",
    "LockfileWriteError",
    "load_entries",
    "replace_entry",
    "save_entries",
]
