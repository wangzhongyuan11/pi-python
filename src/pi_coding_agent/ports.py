"""Stable product service ports used before concrete composition is available."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from pi_ai import JsonValue

from .session.importer import import_pi_session
from .session.models import ImportResult

type ResourceKind = Literal["context", "extension", "prompt", "skill", "theme"]
type ResourceSource = Literal[
    "builtin", "compatibility", "explicit", "global", "package", "project"
]


class Settings(Protocol):
    def get(self, key: str, default: JsonValue = None) -> JsonValue: ...

    def set(self, key: str, value: JsonValue) -> None: ...

    def snapshot(self) -> dict[str, JsonValue]: ...


class InMemorySettings:
    def __init__(self, initial: Mapping[str, JsonValue] | None = None) -> None:
        self._values = dict(initial or {})

    def get(self, key: str, default: JsonValue = None) -> JsonValue:
        return self._values.get(key, default)

    def set(self, key: str, value: JsonValue) -> None:
        self._values[key] = value

    def snapshot(self) -> dict[str, JsonValue]:
        return dict(self._values)


@dataclass(frozen=True, slots=True)
class ResourceDescriptor:
    kind: ResourceKind
    name: str
    path: Path | None
    source: ResourceSource
    metadata: Mapping[str, JsonValue] | None = None


class ResourceLoader(Protocol):
    def discover(self, cwd: Path) -> tuple[ResourceDescriptor, ...]: ...


class NoopResourceLoader:
    def discover(self, cwd: Path) -> tuple[ResourceDescriptor, ...]:
        del cwd
        return ()


class ExtensionRuntime(Protocol):
    async def start(self) -> tuple[ResourceDescriptor, ...]: ...

    async def close(self) -> None: ...


class NoopExtensionRuntime:
    async def start(self) -> tuple[ResourceDescriptor, ...]:
        return ()

    async def close(self) -> None:
        return None


class SessionExporter(Protocol):
    def export(self, transcript: object, destination: Path) -> Path: ...


class NoopSessionExporter:
    def export(self, transcript: object, destination: Path) -> Path:
        del transcript
        return destination.resolve()


class SessionImporter(Protocol):
    def import_session(
        self, source: str | Path, *, session_dir: str | Path | None = None
    ) -> ImportResult: ...


class DefaultSessionImporter:
    def import_session(
        self, source: str | Path, *, session_dir: str | Path | None = None
    ) -> ImportResult:
        return import_pi_session(source, session_dir=session_dir)


__all__ = [
    "DefaultSessionImporter",
    "ExtensionRuntime",
    "InMemorySettings",
    "NoopExtensionRuntime",
    "NoopResourceLoader",
    "NoopSessionExporter",
    "ResourceDescriptor",
    "ResourceKind",
    "ResourceLoader",
    "ResourceSource",
    "SessionExporter",
    "SessionImporter",
    "Settings",
]
