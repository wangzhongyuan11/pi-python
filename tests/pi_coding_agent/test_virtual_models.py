"""Phase 18.5: settings-defined virtual model aliases resolve through --model."""

from __future__ import annotations

import pytest

from pydantic import ValidationError

from pi_coding_agent.config.models import SettingsValues
from pi_coding_agent.model_runtime import (
    ModelRuntime,
    create_model_runtime,
    select_model_argument,
    virtual_models_from_payload,
)


class StaticResolver:
    def resolve(self, provider_id: str) -> dict[str, str]:
        return {"base_url": "https://api.test", "api_key": "k"}


def _runtime() -> ModelRuntime:
    return create_model_runtime(
        credential_resolver=StaticResolver(),  # type: ignore[arg-type]
    )


def test_virtual_models_from_payload_validates_and_normalizes() -> None:
    table = virtual_models_from_payload(
        {
            "fast": {"model": "deepseek-v4-flash", "thinkingLevel": "low"},
            "plain": {"model": "deepseek-v4-pro"},
        }
    )

    assert table["fast"] == ("deepseek-v4-flash", "low")
    assert table["plain"] == ("deepseek-v4-pro", None)


def test_virtual_models_from_payload_drops_malformed_entries() -> None:
    table = virtual_models_from_payload(
        {
            "bad": {"thinkingLevel": "low"},
            "badtype": "not-an-object",
            "ok": {"model": "deepseek-v4-flash"},
        }
    )

    assert list(table) == ["ok"]


def test_select_model_argument_prefers_real_models_over_virtual_names() -> None:
    runtime = _runtime()
    virtual = virtual_models_from_payload({"deepseek-v4-flash": {"model": "deepseek-v4-pro"}})

    model, thinking = select_model_argument(runtime, "deepseek-v4-flash", virtual_models=virtual)

    assert model.id == "deepseek-v4-flash"
    assert thinking is None


def test_select_model_argument_resolves_virtual_alias_with_thinking() -> None:
    runtime = _runtime()
    virtual = virtual_models_from_payload({"fast": {"model": "deepseek-v4-pro"}})

    model, thinking = select_model_argument(runtime, "fast", virtual_models=virtual)

    assert model.id == "deepseek-v4-pro"
    assert thinking is None


def test_select_model_argument_virtual_name_with_unknown_model_raises() -> None:
    runtime = _runtime()
    virtual = virtual_models_from_payload({"ghost": {"model": "no-such-model"}})

    with pytest.raises(Exception, match="unknown model"):
        select_model_argument(runtime, "ghost", virtual_models=virtual)


def test_settings_values_accepts_virtual_models_section() -> None:
    values = SettingsValues.model_validate(
        {"virtualModels": {"fast": {"model": "deepseek-v4-flash", "thinkingLevel": "low"}}}
    )

    assert values.virtual_models["fast"].model == "deepseek-v4-flash"
    assert values.virtual_models["fast"].thinking_level == "low"


def test_settings_values_rejects_virtual_model_without_model_id() -> None:
    with pytest.raises(ValidationError):
        SettingsValues.model_validate({"virtualModels": {"fast": {}}})
