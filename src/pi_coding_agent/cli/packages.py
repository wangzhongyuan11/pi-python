"""CLI placeholder for package commands until the Phase 13 implementation."""

from __future__ import annotations

from typing import TextIO


def run_package_command(arguments: object, *, stdout: TextIO, stderr: TextIO) -> int:
    command = getattr(arguments, "command", "")
    stderr.write(
        f"package command {command!r} is not available in this build; "
        "package management lands in Phase 13\n"
    )
    return 1


__all__ = ["run_package_command"]
