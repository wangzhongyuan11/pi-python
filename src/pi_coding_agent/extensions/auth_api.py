"""Credential persistence port for extensions; secrets never enter messages."""

from __future__ import annotations

from typing import Protocol

from .ui_api import ExtensionUiApi


class CredentialStore(Protocol):
    def get(self, provider: str) -> str | None: ...

    def set(self, provider: str, secret: str) -> None: ...


class CredentialStoreUnavailableError(RuntimeError):
    """A credential operation was requested while no store is configured."""


class ExtensionAuthApi:
    """Reads and stores provider credentials through the configured store."""

    __slots__ = ("_store",)

    def __init__(self, *, store: CredentialStore | None = None) -> None:
        self._store = store

    def _require_store(self) -> CredentialStore:
        if self._store is None:
            raise CredentialStoreUnavailableError(
                "no credential store is configured for extensions"
            )
        return self._store

    def read_secret(self, provider: str) -> str | None:
        return self._require_store().get(provider)

    def store_secret(self, provider: str, secret: str) -> None:
        self._require_store().set(provider, secret)

    async def prompt_for_secret(self, provider: str, ui: ExtensionUiApi) -> str | None:
        secret = ui.request_input(f"API key for {provider}:")
        if secret:
            self.store_secret(provider, secret)
        return secret


__all__ = [
    "CredentialStore",
    "CredentialStoreUnavailableError",
    "ExtensionAuthApi",
]
