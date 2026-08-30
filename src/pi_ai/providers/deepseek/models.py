"""Reviewed DeepSeek model catalog used by the built-in provider."""

from __future__ import annotations

from ...messages import JsonObject
from ...models import Model, ModelCost
from ...usage import ModelThinkingLevel

_COMPAT: JsonObject = {
    "supportsStore": False,
    "supportsDeveloperRole": False,
    "requiresReasoningContentOnAssistantMessages": True,
    "thinkingFormat": "deepseek",
}
_THINKING_LEVELS: dict[ModelThinkingLevel, str | None] = {
    "minimal": None,
    "low": None,
    "medium": None,
    "high": "high",
    "max": "max",
}

DEEPSEEK_MODELS: tuple[Model, ...] = (
    Model(
        id="deepseek-v4-flash",
        name="DeepSeek V4 Flash",
        api="openai-completions",
        provider="deepseek",
        base_url="https://api.deepseek.com",
        reasoning=True,
        input=("text",),
        cost=ModelCost(input=0.44, output=1.32, cache_read=0.014, cache_write=0.0),
        context_window=1_000_000,
        max_tokens=384_000,
        thinking_level_map=_THINKING_LEVELS,
        compat=_COMPAT,
    ),
    Model(
        id="deepseek-v4-pro",
        name="DeepSeek V4 Pro",
        api="openai-completions",
        provider="deepseek",
        base_url="https://api.deepseek.com",
        reasoning=True,
        input=("text",),
        cost=ModelCost(input=1.32, output=3.96, cache_read=0.044, cache_write=0.0),
        context_window=1_000_000,
        max_tokens=384_000,
        thinking_level_map=_THINKING_LEVELS,
        compat=_COMPAT,
    ),
    Model(
        id="deepseek-v4-flash-vision-exp",
        name="DeepSeek V4 Flash Vision (exp)",
        api="openai-completions",
        provider="deepseek",
        base_url="https://api.deepseek.com",
        reasoning=True,
        input=("text", "image"),
        cost=ModelCost(input=0.44, output=1.32, cache_read=0.014, cache_write=0.0),
        context_window=1_000_000,
        max_tokens=384_000,
        thinking_level_map=_THINKING_LEVELS,
        compat=_COMPAT,
    ),
)

_MODELS_BY_ID = {model.id: model for model in DEEPSEEK_MODELS}
DEFAULT_DEEPSEEK_MODEL = _MODELS_BY_ID["deepseek-v4-pro"]


def get_deepseek_model(model_id: str) -> Model:
    return _MODELS_BY_ID[model_id]


__all__ = ["DEEPSEEK_MODELS", "DEFAULT_DEEPSEEK_MODEL", "get_deepseek_model"]
