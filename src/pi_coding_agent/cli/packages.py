"""Package lifecycle command adapter."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import TextIO

from ..config.settings import SettingsManager
from ..packages.manager import DefaultPackageManager


def run_package_command(
    arguments: object,
    *,
    stdout: TextIO,
    stderr: TextIO,
    cwd: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> int:
    command = getattr(arguments, "command", "")
    local = bool(getattr(arguments, "local", False))
    scope = "project" if local else "user"
    trusted = bool(getattr(arguments, "approve", False)) and not bool(
        getattr(arguments, "no_approve", False)
    )
    if local and not trusted:
        stderr.write("Project is not trusted. Use --approve for local package changes.\n")
        return 1
    selected_environ = os.environ if environ is None else environ
    runtime_cwd = Path.cwd() if cwd is None else cwd
    agent_dir = Path(
        selected_environ.get("PI_PYTHON_AGENT_DIR", Path.home() / ".pi-python" / "agent")
    )
    manager = DefaultPackageManager(
        settings=SettingsManager.load(
            agent_dir=agent_dir,
            cwd=runtime_cwd,
            project_trusted=trusted,
        )
    )
    if command == "list":
        packages = manager.list_configured_packages()
        if not packages:
            stdout.write("No packages installed.\n")
            return 0
        for package in packages:
            state = "enabled" if package.enabled else "disabled"
            stdout.write(f"{package.scope}: {package.source} ({state})\n")
        return 0
    if command == "config":
        name = getattr(arguments, "name", None)
        state = getattr(arguments, "state", None)
        if not name or state not in {"enabled", "disabled"}:
            stderr.write("package config requires NAME and enabled|disabled\n")
            return 1
        if not manager.set_enabled(name, state == "enabled", scope=scope):
            stderr.write(f"No package state changed for {name}\n")
            return 1
        return 0
    if command in {"remove", "uninstall"}:
        source = getattr(arguments, "source", "")
        if not manager.remove_installed(source, scope=scope):
            stderr.write(f"No matching package found for {source}\n")
            return 1
        stdout.write(f"Removed {source}\n")
        return 0
    if command == "update":
        source = getattr(arguments, "source", None)
        try:
            updated = manager.update(source, offline=bool(getattr(arguments, "offline", False)))
        except ValueError as error:
            stderr.write(f"{error}\n")
            return 1
        for item in updated:
            stdout.write(f"Updated {item}\n")
        if not updated:
            stdout.write("No packages updated.\n")
        return 0
    stderr.write(
        f"package command {command!r} is not available in this build; "
        "package management lands in Phase 13\n"
    )
    return 1


__all__ = ["run_package_command"]
