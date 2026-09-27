"""Serializable UI bridge for the Node extension host (P15.5-T05).

Dialog requests (input/confirm/select) and one-way notifications (notify,
status) are routed to the product UI. When no UI is attached the bridge
degrades gracefully — dialogs return "declined" sentinels instead of failing
the extension. JavaScript TUI component renderers cannot cross the process
boundary and are reported as structured unsupported capabilities (ADR 0009).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Protocol, cast

from .event_bridge import NodeHostStaleError, NodeRequestError


class NodeUiPort(Protocol):
    """The subset of the product UI the node host may invoke."""

    async def input(self, prompt: str, *, default: str = "") -> str | None: ...

    async def confirm(self, prompt: str) -> bool | None: ...

    async def select(self, title: str, options: tuple[str, ...]) -> str | None: ...

    def notify(self, text: str) -> None: ...

    def set_status(self, key: str, value: str | None) -> None: ...


class NodeUiBridge:
    """Answer host ui_* requests through the attached product UI."""

    def __init__(
        self,
        *,
        ui_provider: Callable[[], NodeUiPort | None],
        generation: int = 0,
    ) -> None:
        self._ui_provider = ui_provider
        self._generation = generation
        self._stale = False

    async def handle_request(self, command: str, payload: Mapping[str, object]) -> object:
        if self._stale:
            raise NodeHostStaleError("node host generation is stale")
        handler = getattr(self, f"_{command}", None)
        if not callable(handler):
            raise NodeRequestError(f"ui bridge cannot handle {command!r}")
        ui = self._ui_provider()
        return await cast("Callable[..., Awaitable[object]]", handler)(payload, ui)

    def invalidate(self) -> None:
        self._stale = True

    async def _ui_input(self, payload: Mapping[str, object], ui: NodeUiPort | None) -> object:
        title = str(payload.get("title", ""))
        placeholder = payload.get("placeholder")
        if ui is None:
            return None
        return await ui.input(title, default=str(placeholder) if placeholder else "")

    async def _ui_confirm(self, payload: Mapping[str, object], ui: NodeUiPort | None) -> object:
        title = str(payload.get("title", ""))
        if ui is None:
            return False
        return bool(await ui.confirm(title))

    async def _ui_select(self, payload: Mapping[str, object], ui: NodeUiPort | None) -> object:
        title = str(payload.get("title", ""))
        raw_options = payload.get("options")
        options = tuple(str(item) for item in cast("list[object]", raw_options or ()))
        if ui is None or not options:
            return None
        return await ui.select(title, options)

    async def _ui_notify(self, payload: Mapping[str, object], ui: NodeUiPort | None) -> object:
        if ui is not None:
            ui.notify(str(payload.get("message", "")))
        return None

    async def _ui_status(self, payload: Mapping[str, object], ui: NodeUiPort | None) -> object:
        if ui is not None:
            ui.set_status("extension", str(payload.get("message", "")) or None)
        return None


__all__ = ["NodeUiBridge", "NodeUiPort"]
