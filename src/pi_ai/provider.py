"""Provider and credential resolution ports."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .context import Context
from .models import Model
from .stream import AssistantStream


@dataclass(frozen=True, slots=True, kw_only=True)
class StreamOptions:
    abort_event: asyncio.Event | None = None


@runtime_checkable
class CredentialResolver(Protocol):
    async def resolve(self, provider: str) -> str | None: ...


@runtime_checkable
class Provider(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def name(self) -> str: ...

    @property
    def models(self) -> tuple[Model, ...]: ...

    def stream(
        self,
        model: Model,
        context: Context,
        options: StreamOptions | None = None,
    ) -> AssistantStream: ...


class StreamFunction(Protocol):
    def __call__(
        self,
        model: Model,
        context: Context,
        options: StreamOptions | None = None,
    ) -> AssistantStream: ...


__all__ = ["CredentialResolver", "Provider", "StreamFunction", "StreamOptions"]
