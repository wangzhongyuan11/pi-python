"""Selected model and Provider stream composition for coding-agent callers."""

from __future__ import annotations

from pi_ai import (
    AssistantStream,
    Context,
    CredentialResolver,
    Model,
    ModelInput,
    ModelThinkingLevel,
    Provider,
    StreamOptions,
)
from pi_ai.providers.deepseek import DEFAULT_DEEPSEEK_MODEL

from .providers import create_builtin_provider


class UnknownModelError(LookupError):
    pass


class ModelCapabilityError(ValueError):
    pass


class ModelRuntime:
    __slots__ = ("_model", "_provider")

    def __init__(self, *, provider: Provider, model: Model) -> None:
        self._provider = provider
        self._model = self._find_model(model)

    @property
    def provider(self) -> Provider:
        return self._provider

    @property
    def models(self) -> tuple[Model, ...]:
        return self._provider.models

    @property
    def model(self) -> Model:
        return self._model

    def select_model(self, model_id: str) -> Model:
        self._model = self._find_model_id(model_id)
        return self._model

    def require_input(self, capability: ModelInput, model: Model | None = None) -> None:
        selected = self._model if model is None else self._find_model(model)
        if capability not in selected.input:
            raise ModelCapabilityError(
                f'model "{selected.provider}/{selected.id}" does not support {capability} input'
            )

    def stream(
        self,
        model: Model,
        context: Context,
        options: StreamOptions | None = None,
    ) -> AssistantStream:
        canonical_model = self._find_model(model)
        return self._provider.stream(canonical_model, context, options)

    def _find_model(self, model: Model) -> Model:
        if model.provider != self._provider.id:
            raise UnknownModelError(f"unknown model for {self._provider.id}: {model.id}")
        return self._find_model_id(model.id)

    def _find_model_id(self, model_id: str) -> Model:
        for model in self._provider.models:
            if model.id == model_id:
                return model
        raise UnknownModelError(f"unknown model for {self._provider.id}: {model_id}")


def create_model_runtime(
    *,
    credential_resolver: CredentialResolver,
    provider_id: str = "deepseek",
    model_id: str | None = None,
    thinking_level: ModelThinkingLevel = "high",
    max_request_retries: int = 0,
    timeout_seconds: float = 300.0,
    max_tokens: int | None = None,
) -> ModelRuntime:
    provider = create_builtin_provider(
        provider_id,
        credential_resolver=credential_resolver,
        thinking_level=thinking_level,
        max_request_retries=max_request_retries,
        timeout_seconds=timeout_seconds,
        max_tokens=max_tokens,
    )
    selected_id = DEFAULT_DEEPSEEK_MODEL.id if model_id is None else model_id
    selected = next((model for model in provider.models if model.id == selected_id), None)
    if selected is None:
        raise UnknownModelError(f"unknown model for {provider.id}: {selected_id}")
    return ModelRuntime(provider=provider, model=selected)


__all__ = [
    "ModelCapabilityError",
    "ModelRuntime",
    "UnknownModelError",
    "create_model_runtime",
]
