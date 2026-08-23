"""DeepSeek credential lookup at the product boundary."""

from __future__ import annotations

import os
import shlex
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from pi_ai.credentials import CredentialFileError, MissingCredentialError

_PROVIDER = "deepseek"
_ENVIRONMENT_VARIABLE = "DEEPSEEK_API_KEY"


def _nonempty(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _read_dotenv_key(path: Path, *, required: bool) -> str | None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        if required:
            raise CredentialFileError(path) from None
        return None
    except (OSError, UnicodeError):
        raise CredentialFileError(path) from None

    for line_number, raw_line in enumerate(lines, start=1):
        try:
            fields = shlex.split(raw_line, comments=True, posix=True)
        except ValueError:
            raise CredentialFileError(path, line=line_number) from None
        if not fields:
            continue
        if fields[0] == "export":
            fields = fields[1:]
        if len(fields) != 1 or "=" not in fields[0]:
            continue
        key, value = fields[0].split("=", 1)
        if key == _ENVIRONMENT_VARIABLE:
            return _nonempty(value)
    return None


@dataclass(slots=True, kw_only=True)
class DeepSeekCredentialResolver:
    api_key: str | None = None
    environ: Mapping[str, str] = field(default_factory=lambda: os.environ)
    env_file: Path | None = None
    cwd: Path = field(default_factory=Path.cwd)

    async def resolve(self, provider: str) -> str | None:
        if provider != _PROVIDER:
            return None

        credential = _nonempty(self.api_key)
        if credential is None:
            credential = _nonempty(self.environ.get(_ENVIRONMENT_VARIABLE))
        if credential is None and self.env_file is not None:
            credential = _read_dotenv_key(self.env_file, required=True)
        if credential is None:
            credential = _read_dotenv_key(self.cwd / ".env", required=False)
        if credential is None:
            raise MissingCredentialError(_PROVIDER, _ENVIRONMENT_VARIABLE)
        return credential


__all__ = ["DeepSeekCredentialResolver"]
