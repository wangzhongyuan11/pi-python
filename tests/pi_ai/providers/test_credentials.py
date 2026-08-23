from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from pi_ai.credentials import CredentialFileError, MissingCredentialError
from pi_coding_agent.deepseek_credentials import DeepSeekCredentialResolver


def resolve(resolver: DeepSeekCredentialResolver, provider: str = "deepseek") -> str | None:
    return asyncio.run(resolver.resolve(provider))


def write_env(path: Path, value: str) -> None:
    path.write_text(f'DEEPSEEK_API_KEY="{value}"\n', encoding="utf-8")


def test_cli_key_wins_without_reading_lower_priority_files(tmp_path: Path) -> None:
    missing = tmp_path / "missing.env"
    resolver = DeepSeekCredentialResolver(
        api_key="cli-secret",
        environ={"DEEPSEEK_API_KEY": "process-secret"},
        env_file=missing,
        cwd=tmp_path,
    )

    assert resolve(resolver) == "cli-secret"


def test_process_environment_wins_over_env_files(tmp_path: Path) -> None:
    explicit = tmp_path / "explicit.env"
    write_env(explicit, "file-secret")
    write_env(tmp_path / ".env", "cwd-secret")

    resolver = DeepSeekCredentialResolver(
        environ={"DEEPSEEK_API_KEY": "process-secret"},
        env_file=explicit,
        cwd=tmp_path,
    )

    assert resolve(resolver) == "process-secret"


def test_explicit_env_file_wins_over_cwd_dotenv(tmp_path: Path) -> None:
    explicit = tmp_path / "explicit.env"
    write_env(explicit, "file-secret")
    write_env(tmp_path / ".env", "cwd-secret")

    resolver = DeepSeekCredentialResolver(environ={}, env_file=explicit, cwd=tmp_path)

    assert resolve(resolver) == "file-secret"


def test_cwd_dotenv_is_the_last_fallback(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "# local only\nexport DEEPSEEK_API_KEY='cwd-secret' # trailing comment\n",
        encoding="utf-8",
    )

    assert resolve(DeepSeekCredentialResolver(environ={}, cwd=tmp_path)) == "cwd-secret"


def test_unrelated_provider_is_not_claimed(tmp_path: Path) -> None:
    resolver = DeepSeekCredentialResolver(api_key="cli-secret", environ={}, cwd=tmp_path)

    assert resolve(resolver, "extension-provider") is None


def test_missing_key_raises_typed_error_without_secret_values(tmp_path: Path) -> None:
    with pytest.raises(MissingCredentialError) as caught:
        resolve(DeepSeekCredentialResolver(environ={}, cwd=tmp_path))

    rendered = f"{caught.value!s} {caught.value!r}"
    assert "DEEPSEEK_API_KEY" in rendered
    assert "secret" not in rendered.lower()


def test_missing_explicit_env_file_is_a_typed_safe_error(tmp_path: Path) -> None:
    path = tmp_path / "missing.env"

    with pytest.raises(CredentialFileError) as caught:
        resolve(DeepSeekCredentialResolver(environ={}, env_file=path, cwd=tmp_path))

    assert str(path) in str(caught.value)
    assert "api_key" not in repr(caught.value).lower()
