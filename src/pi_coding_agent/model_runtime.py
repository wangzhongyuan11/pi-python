"""Selected model and Provider stream composition for coding-agent callers."""

from __future__ import annotations

from dataclasses import replace

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
        return tuple(model for provider in self._providers.values() for model in provider.models)

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
        request_model = (
            canonical_model
            if model.headers == canonical_model.headers
            else replace(canonical_model, headers=model.headers)
        )
        return provider.stream(request_model, context, options)

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


_THINKING_LEVEL_CHOICES = ("off", "minimal", "low", "medium", "high", "xhigh", "max")


type VirtualModelTable = dict[str, tuple[str, ModelThinkingLevel | None]]


def virtual_models_from_payload(payload: object) -> VirtualModelTable:
    """Normalize an untrusted ``virtualModels`` settings payload (bad entries drop)."""

    if not isinstance(payload, dict):
        return {}
    table: VirtualModelTable = {}
    for raw_name, raw_entry in payload.items():
        if not isinstance(raw_name, str) or not raw_name.strip():
            continue
        if not isinstance(raw_entry, dict):
            continue
        model_id = raw_entry.get("model")
        if not isinstance(model_id, str) or not model_id.strip():
            continue
        thinking = raw_entry.get("thinkingLevel")
        level: ModelThinkingLevel | None = (
            thinking if isinstance(thinking, str) and thinking in _THINKING_LEVEL_CHOICES else None
        )
        table[raw_name] = (model_id, level)
    return table


def select_model_argument(
    runtime: ModelRuntime,
    argument: str,
    *,
    virtual_models: VirtualModelTable | None = None,
) -> tuple[Model, ModelThinkingLevel | None]:
    """Resolve a CLI ``--model`` argument and select it on ``runtime``.

    Mirrors the upstream CLI model resolution: canonical ``provider/id``, a bare
    model id, or a unique partial match, plus the ``:<thinking>`` shorthand
    suffix. A suffix that names a valid thinking level is returned to the
    caller so an explicit ``--thinking`` flag can still take precedence; any
    other suffix is ignored and the remaining pattern is matched. Real models
    win over settings-defined virtual aliases that share their name.
    """

    pattern = argument.strip()
    thinking: ModelThinkingLevel | None = None
    head, separator, suffix = pattern.rpartition(":")
    if separator:
        pattern = head
        if suffix in _THINKING_LEVEL_CHOICES:
            thinking = suffix
    try:
        resolved = match_model_argument(runtime, pattern)
    except ValueError:
        table = virtual_models or {}
        entry = table.get(pattern)
        if entry is None:
            raise
        model_id, virtual_thinking = entry
        model = runtime.select_model(model_id)
        return model, thinking if thinking is not None else virtual_thinking
    provider_id, _, model_id = resolved.partition("/")
    model = runtime.select_model(model_id, provider_id=provider_id)
    return model, thinking


__all__ = [
    "ModelCapabilityError",
    "ModelRuntime",
    "UnknownModelError",
    "VirtualModelTable",
    "create_model_runtime",
    "match_model_argument",
    "select_model_argument",
    "virtual_models_from_payload",
]
