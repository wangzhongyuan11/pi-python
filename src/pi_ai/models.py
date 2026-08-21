"""LLM model catalog value objects and thinking-level helpers."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from .messages import JsonObject
from .usage import ModelThinkingLevel

type ModelInput = Literal["text", "image"]


def _require_rate(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{name} must be a number")
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and non-negative")


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelCostRates:
    input: float
    output: float
    cache_read: float
    cache_write: float

    def __post_init__(self) -> None:
        for name in ("input", "output", "cache_read", "cache_write"):
            _require_rate(name, getattr(self, name))


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelCostTier(ModelCostRates):
    input_tokens_above: int

    def __post_init__(self) -> None:
        ModelCostRates.__post_init__(self)
        if isinstance(self.input_tokens_above, bool) or self.input_tokens_above < 0:
            raise ValueError("input_tokens_above must be a non-negative integer")


@dataclass(frozen=True, slots=True, kw_only=True)
class ModelCost(ModelCostRates):
    tiers: tuple[ModelCostTier, ...] | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class Model:
    id: str
    name: str
    api: str
    provider: str
    base_url: str
    reasoning: bool
    input: tuple[ModelInput, ...]
    cost: ModelCost
    context_window: int
    max_tokens: int
    thinking_level_map: Mapping[ModelThinkingLevel, str | None] | None = None
    sampling_params: JsonObject | None = None
    headers: Mapping[str, str] | None = None
    compat: JsonObject | None = None

    def __post_init__(self) -> None:
        if not self.id or not self.name or not self.api or not self.provider or not self.base_url:
            raise ValueError("model identity and endpoint fields must not be empty")
        if isinstance(self.context_window, bool) or self.context_window <= 0:
            raise ValueError("context_window must be a positive integer")
        if isinstance(self.max_tokens, bool) or self.max_tokens <= 0:
            raise ValueError("max_tokens must be a positive integer")
        if not self.input or len(set(self.input)) != len(self.input):
            raise ValueError("input capabilities must be non-empty and unique")
        if any(item not in ("text", "image") for item in self.input):
            raise ValueError("input capabilities must be text or image")
        if self.thinking_level_map is not None:
            object.__setattr__(
                self, "thinking_level_map", MappingProxyType(dict(self.thinking_level_map))
            )
        if self.headers is not None:
            object.__setattr__(self, "headers", MappingProxyType(dict(self.headers)))


_THINKING_LEVELS: tuple[ModelThinkingLevel, ...] = (
    "off",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)


def get_supported_thinking_levels(model: Model) -> tuple[ModelThinkingLevel, ...]:
    if not model.reasoning:
        return ("off",)
    mapping = model.thinking_level_map or {}
    supported: list[ModelThinkingLevel] = []
    for level in _THINKING_LEVELS:
        if level in mapping and mapping[level] is None:
            continue
        if level in ("xhigh", "max") and level not in mapping:
            continue
        supported.append(level)
    return tuple(supported)


def clamp_thinking_level(model: Model, level: ModelThinkingLevel) -> ModelThinkingLevel:
    available = get_supported_thinking_levels(model)
    if level in available:
        return level
    requested_index = _THINKING_LEVELS.index(level)
    for candidate in _THINKING_LEVELS[requested_index:]:
        if candidate in available:
            return candidate
    for candidate in reversed(_THINKING_LEVELS[:requested_index]):
        if candidate in available:
            return candidate
    return available[0]


def models_are_equal(first: Model | None, second: Model | None) -> bool:
    return (
        first is not None
        and second is not None
        and first.id == second.id
        and first.provider == second.provider
    )


__all__ = [
    "Model",
    "ModelCost",
    "ModelCostRates",
    "ModelCostTier",
    "ModelInput",
    "clamp_thinking_level",
    "get_supported_thinking_levels",
    "models_are_equal",
]
