"""Keybinding registry mapping stable action ids to terminal keys."""

from __future__ import annotations

from .actions import TUI_ACTIONS


class KeybindingRegistry:
    """Bidirectional action/key index; unknown actions are rejected."""

    __slots__ = ("_bindings", "_by_key")

    def __init__(self) -> None:
        self._bindings: dict[str, tuple[str, ...]] = {
            action: definition.default_keys for action, definition in TUI_ACTIONS.items()
        }
        self._by_key: dict[str, tuple[str, ...]] = {}
        for action, keys in self._bindings.items():
            for key in keys:
                self._by_key[key] = (*self._by_key.get(key, ()), action)

    def actions(self) -> tuple[str, ...]:
        return tuple(self._bindings)

    def keys_for(self, action: str) -> tuple[str, ...]:
        try:
            return self._bindings[action]
        except KeyError as error:
            raise KeyError(f"unknown tui action: {action}") from error

    def set_keys(self, action: str, *keys: str) -> None:
        if action not in self._bindings:
            raise KeyError(f"unknown tui action: {action}")
        unique: list[str] = []
        for key in keys:
            if key not in unique:
                unique.append(key)
        for key in self._bindings[action]:
            remaining = tuple(candidate for candidate in self._by_key[key] if candidate != action)
            if remaining:
                self._by_key[key] = remaining
            else:
                del self._by_key[key]
        self._bindings[action] = tuple(unique)
        for key in unique:
            self._by_key[key] = (*self._by_key.get(key, ()), action)

    def actions_for(self, key: str) -> tuple[str, ...]:
        return self._by_key.get(key, ())


__all__ = ["KeybindingRegistry"]
