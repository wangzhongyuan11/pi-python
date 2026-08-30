from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from pi_ai import Context, FakeProvider, fake_assistant_message, fake_model
from pi_ai.providers.deepseek import DeepSeekProvider
from pi_coding_agent.model_runtime import (
    ModelCapabilityError,
    ModelRuntime,
    UnknownModelError,
    create_model_runtime,
)
from pi_coding_agent.providers import UnknownProviderError, create_builtin_provider


class StaticResolver:
    async def resolve(self, provider: str) -> str | None:
        return "test-key" if provider == "deepseek" else None


def test_builtin_runtime_defaults_to_deepseek_pro_and_lists_both_models() -> None:
    runtime = create_model_runtime(credential_resolver=StaticResolver())

    assert isinstance(runtime.provider, DeepSeekProvider)
    assert runtime.model.id == "deepseek-v4-pro"
    assert [model.id for model in runtime.models] == [
        "deepseek-v4-flash",
        "deepseek-v4-pro",
        "deepseek-v4-flash-vision-exp",
    ]


def test_runtime_selects_flash_and_rejects_unknown_provider_model_and_capability() -> None:
    runtime = create_model_runtime(
        credential_resolver=StaticResolver(),
        model_id="deepseek-v4-flash",
    )

    assert runtime.model.id == "deepseek-v4-flash"
    with pytest.raises(UnknownModelError, match="missing"):
        runtime.select_model("missing")
    with pytest.raises(ModelCapabilityError, match="image"):
        runtime.require_input("image")
    with pytest.raises(UnknownProviderError, match="other"):
        create_builtin_provider("other", credential_resolver=StaticResolver())


def test_stream_validates_model_ownership_and_delegates_canonical_model() -> None:
    async def scenario() -> tuple[int, str, bool]:
        provider = FakeProvider(
            [fake_assistant_message("done"), fake_assistant_message("canonical")]
        )
        runtime = ModelRuntime(provider=provider, model=provider.models[0])

        terminal = await runtime.stream(
            runtime.model,
            Context(system_prompt="system", messages=()),
        ).result()

        modified = replace(runtime.model, base_url="https://untrusted.invalid")
        await runtime.stream(modified, Context(messages=())).result()

        foreign = create_model_runtime(credential_resolver=StaticResolver()).model
        with pytest.raises(UnknownModelError, match="deepseek-v4-pro"):
            runtime.stream(foreign, Context(messages=()))
        return provider.call_count, terminal.stop_reason, provider.calls[1][0] is runtime.model

    call_count, stop_reason, used_canonical_model = asyncio.run(scenario())

    assert call_count == 2
    assert stop_reason == "stop"
    assert used_canonical_model


def test_extension_provider_registration_selects_and_streams_canonical_model() -> None:
    class OtherProvider(FakeProvider):
        @property
        def id(self) -> str:
            return "other"

        @property
        def models(self):
            return (replace(fake_model(), provider="other", id="other-model"),)

    primary = FakeProvider()
    other = OtherProvider([fake_assistant_message("other answer")])
    runtime = ModelRuntime(provider=primary, model=primary.models[0])

    runtime.register_provider(other)
    selected = runtime.select_model("other-model", provider_id="other")

    assert runtime.provider is other
    assert selected.provider == "other"

    async def stream() -> None:
        await runtime.stream(selected, Context(messages=())).result()

    asyncio.run(stream())
    assert other.call_count == 1
    with pytest.raises(ValueError, match="active"):
        runtime.unregister_provider("other")


def test_create_model_runtime_accepts_provider_model_prefix() -> None:
    runtime = create_model_runtime(
        credential_resolver=StaticResolver(),
        model_id="deepseek/deepseek-v4-flash",
    )

    assert runtime.provider.id == "deepseek"
    assert runtime.model.id == "deepseek-v4-flash"


def test_create_model_runtime_prefix_may_override_default_provider() -> None:
    runtime = create_model_runtime(
        credential_resolver=StaticResolver(),
        provider_id="deepseek",
        model_id="deepseek/deepseek-v4-pro",
    )

    assert runtime.provider.id == "deepseek"
    assert runtime.model.id == "deepseek-v4-pro"


def test_create_model_runtime_rejects_unknown_prefixed_provider() -> None:
    with pytest.raises(UnknownProviderError):
        create_model_runtime(
            credential_resolver=StaticResolver(),
            model_id="openai/gpt-x",
        )
