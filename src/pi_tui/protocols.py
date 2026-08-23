"""Agent-independent UI ports and deterministic test implementation."""

from __future__ import annotations

from typing import Literal, Protocol

type NotificationLevel = Literal["info", "warning", "error"]


class UI(Protocol):
    async def select(self, title: str, options: tuple[str, ...]) -> str | None: ...

    async def confirm(self, prompt: str) -> bool: ...

    async def input(self, prompt: str, *, default: str = "") -> str | None: ...

    def notify(self, message: str, *, level: NotificationLevel = "info") -> None: ...

    def set_status(self, key: str, value: str | None) -> None: ...


class MemoryUI:
    def __init__(
        self,
        *,
        select_result: str | None = None,
        confirm_result: bool = False,
        input_result: str | None = None,
    ) -> None:
        self.select_result = select_result
        self.confirm_result = confirm_result
        self.input_result = input_result
        self.notifications: list[tuple[NotificationLevel, str]] = []
        self.status: dict[str, str] = {}

    async def select(self, title: str, options: tuple[str, ...]) -> str | None:
        del title
        return self.select_result if self.select_result in options else None

    async def confirm(self, prompt: str) -> bool:
        del prompt
        return self.confirm_result

    async def input(self, prompt: str, *, default: str = "") -> str | None:
        del prompt, default
        return self.input_result

    def notify(self, message: str, *, level: NotificationLevel = "info") -> None:
        self.notifications.append((level, message))

    def set_status(self, key: str, value: str | None) -> None:
        if value is None:
            self.status.pop(key, None)
        else:
            self.status[key] = value


class NoopUI(MemoryUI):
    def notify(self, message: str, *, level: NotificationLevel = "info") -> None:
        del message, level

    def set_status(self, key: str, value: str | None) -> None:
        del key, value


__all__ = ["MemoryUI", "NoopUI", "NotificationLevel", "UI"]
