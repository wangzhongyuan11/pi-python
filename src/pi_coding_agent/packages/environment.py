"""Managed extension environment with atomic lockfile and rollback."""

from __future__ import annotations

import re
import shutil
import subprocess
import uuid
from collections.abc import Callable
from pathlib import Path

from .lockfile import LockEntry, load_entries, replace_entry, save_entries
from .resolver import ResolvedSource, resolve_source
from .spec import parse_package_spec


class EnvironmentInstallError(RuntimeError):
    """Installation failed; the previous locked state is preserved."""


type Installer = Callable[[str, Path], None]

LOCKFILE_NAME = "extensions-lock.json"
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_WINDOWS_DEVICE_NAMES = {
    "aux",
    "con",
    "nul",
    "prn",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
}


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
        try:
            _validate_name(name)
        except ValueError as error:
            raise EnvironmentInstallError(f"invalid package name {name!r}: {error}") from error
        env_root = self._root / "env"
        env_root.mkdir(parents=True, exist_ok=True)
        target = env_root / name
        nonce = uuid.uuid4().hex
        staging = env_root / f".{name}.{nonce}.staging"
        backup = env_root / f".{name}.{nonce}.backup"
        previous_entries = self.entries()
        previous_bytes = self.lock_path.read_bytes() if self.lock_path.exists() else None
        try:
            self._installer(_install_requirement(resolved), staging)
            if not staging.is_dir() or _is_link(staging):
                raise RuntimeError("installer did not create a regular package directory")
        except Exception as error:
            _remove_child(staging, env_root, ignore_errors=True)
            raise EnvironmentInstallError(f"install of {name!r} failed: {error}") from error
        entry = LockEntry(
            name=name,
            spec=spec_text,
            location=resolved.location,
            version=resolved.version,
            commit=resolved.commit,
            content_hash=resolved.content_hash,
        )
        previous_moved = False
        activated = False
        try:
            if _path_exists(target):
                target.rename(backup)
                previous_moved = True
            staging.rename(target)
            activated = True
            save_entries(self.lock_path, replace_entry(previous_entries, entry))
        except Exception as error:
            if activated:
                _remove_child(target, env_root, ignore_errors=True)
            if previous_moved and _path_exists(backup):
                backup.rename(target)
            _remove_child(staging, env_root, ignore_errors=True)
            try:
                _restore_lock(self.lock_path, previous_bytes)
            except OSError as restore_error:
                raise EnvironmentInstallError(
                    f"install of {name!r} failed and lock rollback failed: {restore_error}"
                ) from error
            raise EnvironmentInstallError(f"install of {name!r} failed: {error}") from error
        if previous_moved:
            _remove_child(backup, env_root, ignore_errors=True)
        return entry


def _default_name(resolved: ResolvedSource) -> str:
    raw = resolved.location.rstrip("/\\")
    return Path(raw).name or resolved.location


def _validate_name(name: str) -> None:
    if not _SAFE_NAME_RE.fullmatch(name) or name.endswith("."):
        raise ValueError("expected one ASCII path component")
    stem = name.split(".", 1)[0].casefold()
    if stem in _WINDOWS_DEVICE_NAMES:
        raise ValueError("reserved Windows device name")


def _install_requirement(resolved: ResolvedSource) -> str:
    if resolved.kind == "pypi" and resolved.version is not None:
        return f"{resolved.location}=={resolved.version}"
    if resolved.kind == "git" and resolved.commit is not None:
        return f"git+{resolved.location}@{resolved.commit}"
    return resolved.location


def _is_link(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def _path_exists(path: Path) -> bool:
    return path.exists() or _is_link(path)


def _remove_child(path: Path, parent: Path, *, ignore_errors: bool) -> None:
    if path.parent.resolve() != parent.resolve():
        raise RuntimeError(f"refusing to remove path outside environment: {path}")
    try:
        if _is_link(path) or path.is_file():
            path.unlink(missing_ok=True)
        elif path.exists():
            shutil.rmtree(path)
    except OSError:
        if not ignore_errors:
            raise


def _restore_lock(path: Path, previous_bytes: bytes | None) -> None:
    if previous_bytes is None:
        path.unlink(missing_ok=True)
    else:
        path.write_bytes(previous_bytes)


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
