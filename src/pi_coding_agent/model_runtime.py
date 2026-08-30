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
    __slots__ = ("_model", "_provider", "_providers")

    def __init__(self, *, provider: Provider, model: Model) -> None:
        self._provider = provider
        self._providers: dict[str, Provider] = {provider.id: provider}
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

    @property
    def providers(self) -> tuple[Provider, ...]:
        return tuple(self._providers.values())

    def register_provider(self, provider: Provider) -> None:
        existing = self._providers.get(provider.id)
        if existing is not None and existing is not provider:
            raise ValueError(f"provider {provider.id!r} is already registered")
        self._providers[provider.id] = provider

    def unregister_provider(self, provider_id: str) -> None:
        if provider_id == self._provider.id:
            raise ValueError(f"cannot unregister active provider {provider_id!r}")
        self._providers.pop(provider_id, None)

    def select_model(self, model_id: str, *, provider_id: str | None = None) -> Model:
        provider = self._provider if provider_id is None else self._find_provider(provider_id)
        model = self._find_model_id(model_id, provider)
        self._provider = provider
        self._model = model
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
        provider = self._find_provider(canonical_model.provider)
        return provider.stream(canonical_model, context, options)

    def _find_model(self, model: Model) -> Model:
        provider = self._providers.get(model.provider)
        if provider is None:
            raise UnknownModelError(f"unknown model for {model.provider}: {model.id}")
        return self._find_model_id(model.id, provider)

    def _find_model_id(self, model_id: str, provider: Provider | None = None) -> Model:
        selected_provider = self._provider if provider is None else provider
        for model in selected_provider.models:
            if model.id == model_id:
                return model
        raise UnknownModelError(f"unknown model for {selected_provider.id}: {model_id}")

    def _find_provider(self, provider_id: str) -> Provider:
        provider = self._providers.get(provider_id)
        if provider is None:
            raise UnknownModelError(f"unknown provider: {provider_id}")
        return provider


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
    if model_id is not None and "/" in model_id:
        prefixed_provider, _, model_id = model_id.partition("/")
        provider_id = prefixed_provider
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


def match_model_argument(runtime: ModelRuntime, argument: str) -> str:
    """Resolve a user-typed ``--model``/``/model`` argument to ``provider/model``.

    Accepts the canonical ``provider/model`` form, a bare model id, or a unique
    partial match (e.g. ``flash``). Ambiguous or unknown arguments raise a
    ``ValueError`` that lists the available models.
    """

    available = [f"{model.provider}/{model.id}" for model in runtime.models]
    argument = argument.strip()
    if not argument:
        raise ValueError(f"empty model argument; available: {', '.join(available)}")
    if argument in available:
        return argument
    if "/" not in argument:
        bare = [f"{model.provider}/{model.id}" for model in runtime.models if model.id == argument]
        if len(bare) == 1:
            return bare[0]
    lowered = argument.casefold()
    partial = [
        candidate
        for candidate in available
        if lowered in candidate.casefold()
        or candidate.split("/")[-1].casefold().startswith(lowered)
    ]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        raise ValueError(f"ambiguous model {argument!r}; candidates: {', '.join(partial)}")
    raise ValueError(f"unknown model {argument!r}; available: {', '.join(available)}")


__all__ = [
    "ModelCapabilityError",
    "ModelRuntime",
    "UnknownModelError",
    "create_model_runtime",
    "match_model_argument",
]
