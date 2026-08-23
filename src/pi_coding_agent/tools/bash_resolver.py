"""Source-ordered Bash discovery for supported host platforms."""

from __future__ import annotations

import os
import re
import shutil
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import PureWindowsPath

type Exists = Callable[[str], bool]
type Which = Callable[[str, str | None], str | None]


class BashResolutionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class BashConfig:
    executable: str
    arguments: tuple[str, ...]
    command_transport: str


def _default_which(command: str, path: str | None = None) -> str | None:
    return shutil.which(command, path=path)


def _config(executable: str) -> BashConfig:
    normalized = executable.replace("/", "\\").lower()
    legacy_wsl = re.fullmatch(r"[a-z]:\\windows\\(?:system32|sysnative)\\bash\.exe", normalized)
    if legacy_wsl:
        return BashConfig(
            executable=executable,
            arguments=("-s",),
            command_transport="stdin",
        )
    return BashConfig(
        executable=executable,
        arguments=("-c",),
        command_transport="argv",
    )


def resolve_bash(
    *,
    custom_shell_path: str | None = None,
    platform: str | None = None,
    environment: Mapping[str, str] | None = None,
    exists: Exists = os.path.exists,
    which: Which = _default_which,
) -> BashConfig:
    selected_platform = sys.platform if platform is None else platform
    selected_environment = os.environ if environment is None else environment

    if selected_platform == "darwin":
        raise BashResolutionError("macOS is not supported by pi-python")
    if custom_shell_path is not None:
        if exists(custom_shell_path):
            return _config(custom_shell_path)
        raise BashResolutionError(f"Custom shell path not found: {custom_shell_path}")

    if selected_platform == "win32":
        candidates: list[str] = []
        for variable in ("ProgramFiles", "ProgramFiles(x86)"):
            root = selected_environment.get(variable)
            if root:
                candidates.append(str(PureWindowsPath(root) / "Git" / "bin" / "bash.exe"))
        for candidate in candidates:
            if exists(candidate):
                return _config(candidate)

        discovered = which("bash.exe", selected_environment.get("PATH"))
        if discovered is not None and exists(discovered):
            return _config(discovered)
        searched = "\n".join(f"  {candidate}" for candidate in candidates)
        raise BashResolutionError(
            "No bash shell found. Install Git for Windows, add bash.exe to PATH, "
            "or set shellPath in settings.json."
            + (f"\nSearched Git Bash in:\n{searched}" if searched else "")
        )

    if selected_platform == "linux":
        if exists("/bin/bash"):
            return _config("/bin/bash")
        discovered = which("bash", selected_environment.get("PATH"))
        if discovered is not None:
            return _config(discovered)
        raise BashResolutionError(
            "No bash shell found. Install bash, add it to PATH, or set shellPath in settings.json."
        )

    raise BashResolutionError(f"Unsupported platform: {selected_platform}")


__all__ = ["BashConfig", "BashResolutionError", "resolve_bash"]
