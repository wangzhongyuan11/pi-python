from __future__ import annotations

from pi_ai import get_supported_thinking_levels
from pi_ai.providers.deepseek.models import (
    DEEPSEEK_MODELS,
    DEFAULT_DEEPSEEK_MODEL,
    get_deepseek_model,
)


def test_catalog_contains_only_the_controlled_text_models() -> None:
    assert tuple(model.id for model in DEEPSEEK_MODELS) == (
        "deepseek-v4-flash",
        "deepseek-v4-pro",
    )
    assert all(model.provider == "deepseek" for model in DEEPSEEK_MODELS)
    assert all(model.api == "openai-completions" for model in DEEPSEEK_MODELS)
    assert all(model.base_url == "https://api.deepseek.com" for model in DEEPSEEK_MODELS)
    assert all(model.input == ("text",) for model in DEEPSEEK_MODELS)
    assert all(model.context_window == 1_000_000 for model in DEEPSEEK_MODELS)
    assert all(model.max_tokens == 384_000 for model in DEEPSEEK_MODELS)


def test_catalog_defaults_to_pro_and_has_frozen_peak_rates() -> None:
    assert DEFAULT_DEEPSEEK_MODEL.id == "deepseek-v4-pro"
    assert get_deepseek_model("deepseek-v4-pro") is DEFAULT_DEEPSEEK_MODEL

    flash = get_deepseek_model("deepseek-v4-flash")
    assert (flash.cost.input, flash.cost.output, flash.cost.cache_read) == (0.44, 1.32, 0.014)
    assert (
        DEFAULT_DEEPSEEK_MODEL.cost.input,
        DEFAULT_DEEPSEEK_MODEL.cost.output,
        DEFAULT_DEEPSEEK_MODEL.cost.cache_read,
    ) == (1.32, 3.96, 0.044)


def test_models_expose_deepseek_thinking_compatibility() -> None:
    for model in DEEPSEEK_MODELS:
        assert model.reasoning is True
        assert get_supported_thinking_levels(model) == ("off", "high", "max")
        assert model.compat == {
            "supportsStore": False,
            "supportsDeveloperRole": False,
            "requiresReasoningContentOnAssistantMessages": True,
            "thinkingFormat": "deepseek",
        }


def test_unknown_model_is_rejected() -> None:
    try:
        get_deepseek_model("deepseek-v4-flash-vision-exp")
    except KeyError as error:
        assert error.args == ("deepseek-v4-flash-vision-exp",)
    else:
        raise AssertionError("unknown DeepSeek model was accepted")
