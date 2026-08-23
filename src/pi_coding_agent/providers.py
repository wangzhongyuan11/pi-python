"""Built-in Provider factory for the product composition layer."""

from __future__ import annotations

from pi_ai import CredentialResolver, ModelThinkingLevel, Provider, create_deepseek_provider


class UnknownProviderError(LookupError):
    pass


def create_builtin_provider(
    provider_id: str,
    *,
    credential_resolver: CredentialResolver,
    thinking_level: ModelThinkingLevel = "high",
    max_request_retries: int = 0,
    timeout_seconds: float = 300.0,
    max_tokens: int | None = None,
) -> Provider:
    if provider_id != "deepseek":
        raise UnknownProviderError(f"unknown built-in provider: {provider_id}")
    return create_deepseek_provider(
        credential_resolver=credential_resolver,
        thinking_level=thinking_level,
        max_request_retries=max_request_retries,
        timeout_seconds=timeout_seconds,
        max_tokens=max_tokens,
    )


__all__ = ["UnknownProviderError", "create_builtin_provider"]
