from __future__ import annotations

from collections.abc import Callable, Mapping

import pytest

from pi_coding_agent.tools.bash_resolver import BashResolutionError, resolve_bash


def _exists(*paths: str) -> Callable[[str], bool]:
    available = set(paths)

    def exists(path: str) -> bool:
        return path in available

    return exists


def _which(results: Mapping[str, str]) -> Callable[[str, str | None], str | None]:
    def which(command: str, _path: str | None = None) -> str | None:
        return results.get(command)

    return which


def test_explicit_shell_path_has_highest_priority() -> None:
    config = resolve_bash(
        custom_shell_path=r"D:\Portable\bash.exe",
        platform="win32",
        environment={"ProgramFiles": r"C:\Program Files"},
        exists=_exists(r"D:\Portable\bash.exe", r"C:\Program Files\Git\bin\bash.exe"),
        which=_which({"bash.exe": r"C:\Path\bash.exe"}),
    )

    assert config.executable == r"D:\Portable\bash.exe"
    assert config.arguments == ("-c",)
    assert config.command_transport == "argv"


def test_missing_explicit_shell_is_an_error() -> None:
    with pytest.raises(BashResolutionError, match="Custom shell path not found"):
        resolve_bash(
            custom_shell_path=r"D:\missing\bash.exe",
            platform="win32",
            environment={},
            exists=_exists(),
            which=_which({}),
        )


def test_windows_prefers_git_bash_before_path() -> None:
    git_bash = r"C:\Program Files\Git\bin\bash.exe"
    config = resolve_bash(
        platform="win32",
        environment={"ProgramFiles": r"C:\Program Files", "PATH": r"C:\Path"},
        exists=_exists(git_bash, r"C:\Path\bash.exe"),
        which=_which({"bash.exe": r"C:\Path\bash.exe"}),
    )

    assert config.executable == git_bash


def test_windows_legacy_wsl_bash_uses_stdin_transport() -> None:
    legacy = r"C:\Windows\System32\bash.exe"
    config = resolve_bash(
        platform="win32",
        environment={"PATH": r"C:\Windows\System32"},
        exists=_exists(legacy),
        which=_which({"bash.exe": legacy}),
    )

    assert config.executable == legacy
    assert config.arguments == ("-s",)
    assert config.command_transport == "stdin"


def test_linux_prefers_bin_bash_then_path() -> None:
    direct = resolve_bash(
        platform="linux",
        environment={"PATH": "/custom/bin"},
        exists=_exists("/bin/bash"),
        which=_which({"bash": "/custom/bin/bash"}),
    )
    fallback = resolve_bash(
        platform="linux",
        environment={"PATH": "/custom/bin"},
        exists=_exists("/custom/bin/bash"),
        which=_which({"bash": "/custom/bin/bash"}),
    )

    assert direct.executable == "/bin/bash"
    assert fallback.executable == "/custom/bin/bash"


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_missing_bash_has_actionable_install_diagnostic(platform: str) -> None:
    with pytest.raises(BashResolutionError) as captured:
        resolve_bash(
            platform=platform,
            environment={},
            exists=_exists(),
            which=_which({}),
        )

    message = str(captured.value)
    assert "No bash shell found" in message
    assert "shellPath" in message


def test_macos_is_explicitly_unsupported() -> None:
    with pytest.raises(BashResolutionError, match="macOS is not supported"):
        resolve_bash(
            platform="darwin",
            environment={},
            exists=_exists(),
            which=_which({}),
        )
