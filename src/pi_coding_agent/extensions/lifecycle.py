"""Generation-scoped extension teardown; stale registrations stay inert."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass


class LifecycleClosedError(RuntimeError):
    """Registration was attempted after teardown without a new generation."""


@dataclass(frozen=True, slots=True)
class TeardownToken:
    generation: int
    identifier: int


class ExtensionLifecycle:
    """Teardown handlers fire exactly once per generation, newest first."""

    __slots__ = (
        "_closed",
        "_generation",
        "_next_identifier",
        "_teardowns",
        "unregistered_count",
    )

    def __init__(self) -> None:
        self._generation = 0
        self._teardowns: dict[int, Callable[[], object]] = {}
        self._next_identifier = 0
        self._closed = False
        self.unregistered_count = 0

    @property
    def active(self) -> bool:
        return not self._closed

    def register_teardown(self, handler: Callable[[], object]) -> TeardownToken:
        if self._closed:
            raise LifecycleClosedError("extension lifecycle is torn down")
        identifier = self._next_identifier
        self._next_identifier += 1
        self._teardowns[identifier] = handler
        return TeardownToken(generation=self._generation, identifier=identifier)

    def unregister(self, token: TeardownToken) -> None:
        if token.generation != self._generation or self._closed:
            return
        if self._teardowns.pop(token.identifier, None) is not None:
            self.unregistered_count += 1

    def begin_generation(self) -> None:
        """Reopen registration for a reloaded set of extensions."""
        if not self._closed:
            raise LifecycleClosedError("active extension generation must be torn down first")
        self._generation += 1
        self._closed = False

    def teardown(self) -> tuple[BaseException, ...]:
        if self._closed:
            return ()
        self._closed = True
        handlers = tuple(reversed(self._teardowns.values()))
        self._teardowns.clear()
        errors: list[BaseException] = []
        for handler in handlers:
            try:
                handler()
            except Exception as error:
                errors.append(error)
        return tuple(errors)

    async def teardown_async(self) -> tuple[BaseException, ...]:
        if self._closed:
            return ()
        self._closed = True
        handlers = tuple(reversed(self._teardowns.values()))
        self._teardowns.clear()
        errors: list[BaseException] = []
        for handler in handlers:
            try:
                result = handler()
                if inspect.isawaitable(result):
                    await result
            except Exception as error:
                errors.append(error)
        return tuple(errors)


__all__ = ["ExtensionLifecycle", "LifecycleClosedError", "TeardownToken"]
