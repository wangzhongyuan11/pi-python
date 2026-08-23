from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from pi_ai import Context, FakeProvider, fake_assistant_message
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
