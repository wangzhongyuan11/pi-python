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
    handler: Callable[..., CommandResult | Awaitable[CommandResult]]


def _error(text: str) -> CommandOutcome:
    return CommandOutcome(kind="error", text=text)


class CommandDispatcher:
    """Routes ``/name args`` input lines to registered handlers."""

    __slots__ = ("_commands", "_context")

    def __init__(self, *, context: object | None = None) -> None:
        self._commands: dict[str, CommandSpec] = {}
        self._context = context

    @classmethod
    def from_registry(
        cls, registry: CapabilityRegistry, *, context: object | None = None
    ) -> CommandDispatcher:
        dispatcher = cls(context=context)
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
                            "Callable[..., CommandResult | Awaitable[CommandResult]]",
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
            result = _invoke_with_optional_context(spec.handler, args.strip(), self._context)
            if inspect.isawaitable(result):
                result = await result
        except Exception as error:
            return _error(f"/{name} failed: {error}")
        if isinstance(result, str):
            return CommandOutcome(kind="message", text=result)
        return result or CommandOutcome(kind="none")


class ShortcutDispatcher:
    """Routes normalized TUI key identifiers to extension handlers."""

    __slots__ = ("_context", "_shortcuts")

    def __init__(self, *, context: object | None = None) -> None:
        self._context = context
        self._shortcuts: dict[str, Callable[..., object]] = {}

    @classmethod
    def from_registry(
        cls, registry: CapabilityRegistry, *, context: object | None = None
    ) -> ShortcutDispatcher:
        dispatcher = cls(context=context)
        for registration in registry.registrations("shortcut"):
            if callable(registration.payload):
                dispatcher._shortcuts[_normalize_shortcut(registration.name)] = registration.payload
        return dispatcher

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._shortcuts)

    async def dispatch(self, name: str) -> bool:
        handler = self._shortcuts.get(_normalize_shortcut(name))
        if handler is None:
            return False
        try:
            result = _invoke_shortcut(handler, self._context)
            if inspect.isawaitable(result):
                await result
        except Exception:
            # Shortcut failures must not terminate the interactive input loop.
            return True
        return True


def _invoke_with_optional_context(
    handler: Callable[..., CommandResult | Awaitable[CommandResult]],
    args: str,
    context: object | None,
) -> CommandResult | Awaitable[CommandResult]:
    if context is not None and _accepts(handler, args, context):
        return handler(args, context)
    return handler(args)


def _invoke_shortcut(handler: Callable[..., object], context: object | None) -> object:
    if context is not None and _accepts(handler, context):
        return handler(context)
    return handler()


def _accepts(handler: Callable[..., object], *args: object) -> bool:
    try:
        inspect.signature(handler).bind(*args)
    except (TypeError, ValueError):
        return False
    return True


def _normalize_shortcut(name: str) -> str:
    return "+".join(part.strip().casefold() for part in name.split("+") if part.strip())


__all__ = ["CommandDispatcher", "CommandOutcome", "CommandSpec", "ShortcutDispatcher"]
