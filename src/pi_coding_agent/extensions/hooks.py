"""Uniform hook execution: sync or async handlers, isolated failures."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HookOutcome:
    ok: bool
    value: object | None = None
    error: BaseException | None = None


Handler = Callable[..., object]


class HookRunner:
    """Invokes registered handlers in order; third-party errors never escape."""

    __slots__ = ("_handlers",)

    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = {}

    def register(self, event: str, handler: Handler) -> Callable[[], None]:
        self._handlers.setdefault(event, []).append(handler)

        def unregister() -> None:
            handlers = self._handlers.get(event)
            if handlers and handler in handlers:
                handlers.remove(handler)

        return unregister

    async def emit(self, event: str, /, *args: object, **kwargs: object) -> list[HookOutcome]:
        outcomes: list[HookOutcome] = []
        for handler in tuple(self._handlers.get(event, ())):
            outcomes.append(await invoke_hook(handler, *args, **kwargs))
        return outcomes


async def invoke_hook(handler: Handler, /, *args: object, **kwargs: object) -> HookOutcome:
    try:
        result = handler(*args, **kwargs)
        if inspect.isawaitable(result):
            result = await result
    except asyncio.CancelledError:
        raise
    except Exception as error:
        return HookOutcome(ok=False, error=error)
    return HookOutcome(ok=True, value=result)


__all__ = ["HookOutcome", "HookRunner", "invoke_hook"]
