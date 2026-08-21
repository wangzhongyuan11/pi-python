"""Token usage, cost, and thinking-level value objects."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from pydantic import ConfigDict, TypeAdapter

type ThinkingLevel = Literal["minimal", "low", "medium", "high", "xhigh", "max"]
type ModelThinkingLevel = Literal["off", "minimal", "low", "medium", "high", "xhigh", "max"]

_THINKING_LEVEL_ADAPTER = TypeAdapter[ThinkingLevel](ThinkingLevel, config=ConfigDict(strict=True))
_MODEL_THINKING_LEVEL_ADAPTER = TypeAdapter[ModelThinkingLevel](
    ModelThinkingLevel,
    config=ConfigDict(strict=True),
)


def _require_nonnegative_number(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{name} must be a number")
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and non-negative")


def _require_nonnegative_integer(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


@dataclass(frozen=True, slots=True, kw_only=True)
class UsageCost:
    input: float
    output: float
    cache_read: float
    cache_write: float
    total: float

    def __post_init__(self) -> None:
        for name in ("input", "output", "cache_read", "cache_write", "total"):
            _require_nonnegative_number(name, getattr(self, name))


@dataclass(frozen=True, slots=True, kw_only=True)
class Usage:
    input: int
    output: int
    cache_read: int
    cache_write: int
    total_tokens: int
    cost: UsageCost
    cache_write_1h: int | None = None
    reasoning: int | None = None

    def __post_init__(self) -> None:
        for name in ("input", "output", "cache_read", "cache_write", "total_tokens"):
            _require_nonnegative_integer(name, getattr(self, name))
        if self.cache_write_1h is not None:
            _require_nonnegative_integer("cache_write_1h", self.cache_write_1h)
            if self.cache_write_1h > self.cache_write:
                raise ValueError("cache_write_1h cannot exceed cache_write")
        if self.reasoning is not None:
            _require_nonnegative_integer("reasoning", self.reasoning)
            if self.reasoning > self.output:
                raise ValueError("reasoning cannot exceed output")


def validate_thinking_level(value: object) -> ThinkingLevel:
    return _THINKING_LEVEL_ADAPTER.validate_python(value)


def validate_model_thinking_level(value: object) -> ModelThinkingLevel:
    return _MODEL_THINKING_LEVEL_ADAPTER.validate_python(value)


__all__ = [
    "ModelThinkingLevel",
    "ThinkingLevel",
    "Usage",
    "UsageCost",
    "validate_model_thinking_level",
    "validate_thinking_level",
]
