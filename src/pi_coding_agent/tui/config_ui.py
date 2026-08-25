"""Model and thinking-level selectors with capability clamping."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

THINKING_LEVELS: tuple[str, ...] = (
    "off",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)


@dataclass(frozen=True, slots=True)
class ModelOption:
    id: str
    name: str
    max_thinking: str = "max"


def _clamp(level: str, maximum: str) -> str:
    if level not in THINKING_LEVELS or maximum not in THINKING_LEVELS:
        raise ValueError(f"unknown thinking level: {level!r} / {maximum!r}")
    ceiling = THINKING_LEVELS.index(maximum)
    position = THINKING_LEVELS.index(level)
    return THINKING_LEVELS[min(position, ceiling)]


class ModelSettingsSelector:
    """Cycles models and thinking levels; persists through ``on_change``."""

    __slots__ = ("_index", "_models", "_on_change", "_thinking")

    def __init__(
        self,
        models: Sequence[ModelOption],
        *,
        current_model_id: str,
        current_thinking: str = "medium",
        on_change: Callable[[str, str], None] | None = None,
    ) -> None:
        self._models: tuple[ModelOption, ...] = tuple(models)
        ids = [model.id for model in self._models]
        if current_model_id not in ids:
            raise ValueError(f"unknown model id: {current_model_id}")
        self._index = ids.index(current_model_id)
        self._on_change = on_change
        self._thinking = _clamp(current_thinking, self._current.max_thinking)

    @property
    def _current(self) -> ModelOption:
        return self._models[self._index]

    @property
    def current_model_id(self) -> str:
        return self._current.id

    @property
    def current_thinking(self) -> str:
        return self._thinking

    def cycle_model(self) -> None:
        self._index = (self._index + 1) % len(self._models)
        self._thinking = _clamp(self._thinking, self._current.max_thinking)

    def cycle_thinking(self) -> None:
        ceiling = THINKING_LEVELS.index(self._current.max_thinking)
        allowed = THINKING_LEVELS[: ceiling + 1]
        position = allowed.index(_clamp(self._thinking, self._current.max_thinking))
        self._thinking = allowed[(position + 1) % len(allowed)]

    def set_thinking(self, level: str) -> None:
        if level not in THINKING_LEVELS:
            raise ValueError(f"unknown thinking level: {level}")
        clamped = _clamp(level, self._current.max_thinking)
        if clamped != level:
            raise ValueError(
                f"thinking level {level!r} exceeds capability {self._current.max_thinking!r}"
            )
        self._thinking = clamped

    def confirm(self) -> None:
        if self._on_change is not None:
            self._on_change(self.current_model_id, self.current_thinking)


__all__ = ["ModelOption", "ModelSettingsSelector", "THINKING_LEVELS"]
