"""Managed extension environment with atomic lockfile and rollback."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from .lockfile import LockEntry, load_entries, replace_entry, save_entries
from .resolver import ResolvedSource, resolve_source
from .spec import parse_package_spec


class EnvironmentInstallError(RuntimeError):
    """Installation failed; the previous locked state is preserved."""


type Installer = Callable[[str, Path], None]

LOCKFILE_NAME = "extensions-lock.json"


class ManagedEnvironment:
    """Installs resolved packages under ``root/env`` and locks them atomically."""

    __slots__ = ("_installer", "_root")

    def __init__(self, *, root: Path, installer: Installer | None = None) -> None:
        self._root = root.resolve()
        self._installer: Installer = installer or _uv_installer

    @property
    def lock_path(self) -> Path:
        return self._root / LOCKFILE_NAME

    def entries(self) -> tuple[LockEntry, ...]:
        return load_entries(self.lock_path)

    def install(self, spec_text: str) -> LockEntry:
        return self._apply(spec_text)

    def update(self, name: str, spec_text: str) -> LockEntry:
        return self._apply(spec_text, expected_name=name)

    # ------------------------------------------------------------------

    def _apply(self, spec_text: str, *, expected_name: str | None = None) -> LockEntry:
        try:
            resolved = resolve_source(parse_package_spec(spec_text))
        except Exception as error:
            raise EnvironmentInstallError(f"cannot resolve {spec_text!r}: {error}") from error
        name = expected_name or _default_name(resolved)
        target = self._root / "env" / name
        previous_entries = self.entries()
        previous_bytes = self.lock_path.read_bytes() if self.lock_path.exists() else None
        try:
            if target.exists():
                shutil.rmtree(target)
            self._installer(resolved.location, target)
        except Exception as error:
            shutil.rmtree(target, ignore_errors=True)
            raise EnvironmentInstallError(f"install of {name!r} failed: {error}") from error
        entry = LockEntry(
            name=name,
            spec=spec_text,
            location=resolved.location,
            version=resolved.version,
            commit=resolved.commit,
            content_hash=resolved.content_hash,
        )
        try:
            save_entries(self.lock_path, replace_entry(previous_entries, entry))
        except Exception as error:
            shutil.rmtree(target, ignore_errors=True)
            if previous_bytes is not None:
                self.lock_path.write_bytes(previous_bytes)
            raise EnvironmentInstallError(f"locking {name!r} failed: {error}") from error
        return entry


def _default_name(resolved: ResolvedSource) -> str:
    raw = resolved.location.rstrip("/\\")
    return Path(raw).name or resolved.location


def _uv_installer(source_location: str, target_dir: Path) -> None:
    completed = subprocess.run(
        ["uv", "pip", "install", "--target", str(target_dir), source_location],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"uv pip install failed: {completed.stderr.strip()}")


__all__ = ["EnvironmentInstallError", "Installer", "ManagedEnvironment"]
