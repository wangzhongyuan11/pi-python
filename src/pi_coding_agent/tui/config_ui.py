"""Model and thinking-level selectors with capability clamping."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import cast

from pi_ai import ModelThinkingLevel, clamp_thinking_level

from ..agent_session import AgentSession
from ..model_runtime import ModelRuntime
from ..session.models import ModelChangeEntry, ThinkingLevelChangeEntry

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


class ModelSettingsController:
    """Applies a validated selection to the live Agent and append-only Session."""

    __slots__ = ("_entry_id_factory", "_model_runtime", "_session", "_timestamp_factory")

    def __init__(
        self,
        *,
        session: AgentSession,
        model_runtime: ModelRuntime,
        entry_id_factory: Callable[[], str],
        timestamp_factory: Callable[[], str],
    ) -> None:
        self._session = session
        self._model_runtime = model_runtime
        self._entry_id_factory = entry_id_factory
        self._timestamp_factory = timestamp_factory

    def apply(self, model_id: str, thinking_level: str) -> None:
        if thinking_level not in THINKING_LEVELS:
            raise ValueError(f"unknown thinking level: {thinking_level}")
        current = self._session.state
        selected = self._model_runtime.select_model(model_id)
        requested = cast("ModelThinkingLevel", thinking_level)
        if clamp_thinking_level(selected, requested) != requested:
            raise ValueError(
                f"thinking level {thinking_level!r} exceeds capability of {selected.id!r}"
            )
        manager = self._session.session_manager
        if current.model != selected:
            manager.append(
                ModelChangeEntry(
                    type="model_change",
                    id=self._entry_id_factory(),
                    parent_id=manager.leaf_id,
                    timestamp=self._timestamp_factory(),
                    provider=selected.provider,
                    model_id=selected.id,
                )
            )
        if current.thinking_level != requested:
            manager.append(
                ThinkingLevelChangeEntry(
                    type="thinking_level_change",
                    id=self._entry_id_factory(),
                    parent_id=manager.leaf_id,
                    timestamp=self._timestamp_factory(),
                    thinking_level=requested,
                )
            )
        self._session.agent.set_model(selected)
        self._session.agent.set_thinking_level(requested)


__all__ = [
    "ModelOption",
    "ModelSettingsController",
    "ModelSettingsSelector",
    "THINKING_LEVELS",
]
