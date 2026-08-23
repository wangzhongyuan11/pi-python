"""Canonical project trust decisions stored independently of resource loading."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from threading import RLock
from typing import Protocol, cast

from ..session.atomic import atomic_write


class TrustStoreError(ValueError):
    pass


class TrustDecision(str, Enum):
    TRUSTED = "trusted"
    UNTRUSTED = "untrusted"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True, kw_only=True)
class TrustEntry:
    path: Path
    decision: TrustDecision


class ProjectTrustStore(Protocol):
    def get(self, cwd: Path) -> TrustDecision: ...

    def get_entry(self, cwd: Path) -> TrustEntry | None: ...

    def set(self, cwd: Path, decision: TrustDecision) -> None: ...


def canonical_project_path(path: Path) -> Path:
    return path.expanduser().resolve()


class FileProjectTrustStore:
    def __init__(self, path: Path) -> None:
        self._path = path.expanduser().resolve()
        self._lock = RLock()

    def _read(self) -> dict[str, bool]:
        if not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise TrustStoreError(f"failed to read trust store {self._path}: {error}") from error
        if not isinstance(raw, dict):
            raise TrustStoreError(f"invalid trust store {self._path}: expected object")
        data: dict[str, bool] = {}
        for key, value in cast(dict[object, object], raw).items():
            if not isinstance(key, str) or not isinstance(value, bool):
                raise TrustStoreError(
                    f"invalid trust store {self._path}: entries must map paths to booleans"
                )
            data[key] = value
        return data

    def get_entry(self, cwd: Path) -> TrustEntry | None:
        with self._lock:
            data = self._read()
        current = canonical_project_path(cwd)
        while True:
            value = data.get(str(current))
            if value is not None:
                return TrustEntry(
                    path=current,
                    decision=TrustDecision.TRUSTED if value else TrustDecision.UNTRUSTED,
                )
            if current.parent == current:
                return None
            current = current.parent

    def get(self, cwd: Path) -> TrustDecision:
        entry = self.get_entry(cwd)
        return TrustDecision.UNKNOWN if entry is None else entry.decision

    def set(self, cwd: Path, decision: TrustDecision) -> None:
        key = str(canonical_project_path(cwd))
        with self._lock:
            data = self._read()
            if decision is TrustDecision.UNKNOWN:
                data.pop(key, None)
            else:
                data[key] = decision is TrustDecision.TRUSTED
            encoded = json.dumps(dict(sorted(data.items())), indent=2, ensure_ascii=False)
            atomic_write(self._path, f"{encoded}\n".encode())


__all__ = [
    "FileProjectTrustStore",
    "ProjectTrustStore",
    "TrustDecision",
    "TrustEntry",
    "TrustStoreError",
    "canonical_project_path",
]
