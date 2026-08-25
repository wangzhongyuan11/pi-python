"""Generation-scoped extension teardown; stale registrations stay inert."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


class LifecycleClosedError(RuntimeError):
    """Registration was attempted after teardown without a new generation."""


@dataclass(frozen=True, slots=True)
class TeardownToken:
    generation: int
    index: int


class ExtensionLifecycle:
    """Teardown handlers fire exactly once per generation, newest first."""

    __slots__ = ("_closed", "_generation", "_teardowns", "unregistered_count")

    def __init__(self) -> None:
        self._generation = 0
        self._teardowns: list[Callable[[], object]] = []
        self._closed = False
        self.unregistered_count = 0

    @property
    def active(self) -> bool:
        return not self._closed

    def register_teardown(self, handler: Callable[[], object]) -> TeardownToken:
        if self._closed:
            raise LifecycleClosedError("extension lifecycle is torn down")
        self._teardowns.append(handler)
        return TeardownToken(generation=self._generation, index=len(self._teardowns) - 1)

    def unregister(self, token: TeardownToken) -> None:
        if token.generation != self._generation or self._closed:
            return
        if 0 <= token.index < len(self._teardowns):
            del self._teardowns[token.index]
            self.unregistered_count += 1

    def begin_generation(self) -> None:
        """Reopen registration for a reloaded set of extensions."""
        self._closed = False

    def teardown(self) -> None:
        if self._closed:
            return
        while self._teardowns:
            handler = self._teardowns.pop()
            handler()
        self._closed = True


__all__ = ["ExtensionLifecycle", "LifecycleClosedError", "TeardownToken"]
