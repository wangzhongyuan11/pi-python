"""Slash-command dispatch for the interactive product TUI."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, cast

from ..extensions.registry import CapabilityRegistry, RegistryConflictError

type CommandResult = CommandOutcome | str | None


@dataclass(frozen=True, slots=True)
class CommandOutcome:
    kind: Literal["message", "error", "none", "raw"]
    text: str = ""


@dataclass(frozen=True, slots=True)
class CommandSpec:
    name: str
    source: str
    handler: Callable[[str], CommandResult | Awaitable[CommandResult]]


def _error(text: str) -> CommandOutcome:
    return CommandOutcome(kind="error", text=text)


class CommandDispatcher:
    """Routes ``/name args`` input lines to registered handlers."""

    __slots__ = ("_commands",)

    def __init__(self) -> None:
        self._commands: dict[str, CommandSpec] = {}

    @classmethod
    def from_registry(cls, registry: CapabilityRegistry) -> CommandDispatcher:
        dispatcher = cls()
        dispatcher.register_registry(registry)
        return dispatcher

    def register_registry(self, registry: CapabilityRegistry) -> tuple[str, ...]:
        """Import extension commands; conflicting names are skipped and reported."""

        skipped: list[str] = []
        for registration in registry.registrations("command"):
            if not callable(registration.payload):
                continue
            try:
                self.register(
                    CommandSpec(
                        name=registration.name,
                        source=registration.source,
                        handler=cast(
                            "Callable[[str], CommandResult | Awaitable[CommandResult]]",
                            registration.payload,
                        ),
                    )
                )
            except RegistryConflictError:
                skipped.append(registration.name)
        return tuple(skipped)

    def register(self, spec: CommandSpec) -> None:
        if spec.name in self._commands:
            raise RegistryConflictError(
                f"command /{spec.name} already registered by {self._commands[spec.name].source!r}"
            )
        self._commands[spec.name] = spec

    async def dispatch(self, line: str) -> CommandOutcome | None:
        stripped = line.strip()
        if not stripped.startswith("/"):
            return None
        body = stripped[1:]
        name, _, args = body.partition(" ")
        spec = self._commands.get(name)
        if spec is None:
            return _error(f"unknown command: /{name}")
        try:
            result = spec.handler(args.strip())
            if inspect.isawaitable(result):
                result = await result
        except Exception as error:
            return _error(f"/{name} failed: {error}")
        if isinstance(result, str):
            return CommandOutcome(kind="message", text=result)
        return result or CommandOutcome(kind="none")


__all__ = ["CommandDispatcher", "CommandOutcome", "CommandSpec"]
