"""Safe, provider-neutral credential resolution errors."""

from __future__ import annotations

from pathlib import Path


class CredentialResolutionError(RuntimeError):
    """Base error for credential lookup failures."""


class MissingCredentialError(CredentialResolutionError):
    def __init__(self, provider: str, environment_variable: str) -> None:
        super().__init__(
            f"No credential configured for {provider}; set {environment_variable} "
            "or provide an explicit API key"
        )
        self.provider = provider
        self.environment_variable = environment_variable


class CredentialFileError(CredentialResolutionError):
    def __init__(self, path: Path, *, line: int | None = None) -> None:
        location = f"{path}:{line}" if line is not None else str(path)
        super().__init__(f"Could not read credential file {location}")
        self.path = path
        self.line = line


__all__ = ["CredentialFileError", "CredentialResolutionError", "MissingCredentialError"]
