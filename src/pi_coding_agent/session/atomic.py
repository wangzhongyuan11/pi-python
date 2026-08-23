"""Crash-resistant whole-file output for fork, import, and migration paths."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def _sync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write(path: str | Path, data: bytes) -> None:
    """Durably replace one file without exposing a partially written target."""

    target = Path(path).resolve()
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, target)
        _sync_directory(target.parent)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def atomic_create(path: str | Path, data: bytes) -> None:
    """Durably create one new file, failing atomically if the target already exists."""

    target = Path(path).resolve()
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        temporary.chmod(0o600)
        os.link(temporary, target)
        temporary.unlink()
        _sync_directory(target.parent)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


__all__ = ["atomic_create", "atomic_write"]
