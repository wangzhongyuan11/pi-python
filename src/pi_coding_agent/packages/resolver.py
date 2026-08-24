"""Resolve extension package specs into source identity and content hashes."""

from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .spec import PackageSpec, is_pinned_commit

type CommandRunner = Callable[[Sequence[str]], str]

_EXCLUDED_DIRS = {"__pycache__", ".git", ".venv", "dist", "node_modules"}


class PackageResolutionError(RuntimeError):
    """Base error for failed package source resolution."""


class RefDriftError(PackageResolutionError):
    """The remote ref resolved to a different commit than the pinned SHA."""


class OfflineResolutionError(PackageResolutionError):
    """Resolution needed the network but the runner could not reach it."""


@dataclass(frozen=True, slots=True)
class ResolvedSource:
    kind: str
    location: str
    version: str | None
    commit: str | None
    content_hash: str | None


def _default_runner(command: Sequence[str]) -> str:
    try:
        completed = subprocess.run(
            list(command), check=True, capture_output=True, text=True, encoding="utf-8"
        )
    except OSError as error:
        raise OfflineResolutionError(f"cannot run {command[0]!r}: {error}") from error
    return completed.stdout


def resolve_source(
    spec: PackageSpec,
    *,
    runner: CommandRunner | None = None,
    root: Path | None = None,
) -> ResolvedSource:
    run = runner if runner is not None else _default_runner
    if spec.kind == "local":
        return _resolve_local(spec, root)
    if spec.kind == "git":
        return _resolve_git(spec, run)
    return ResolvedSource(
        kind="pypi",
        location=spec.location,
        version=spec.rev,
        commit=None,
        content_hash=None,
    )


def _resolve_local(spec: PackageSpec, root: Path | None) -> ResolvedSource:
    base = root if root is not None else Path.cwd()
    path = Path(spec.location)
    absolute = (path if path.is_absolute() else base / path).resolve()
    digest = hashlib.sha256()
    for file in sorted(absolute.rglob("*")):
        if not file.is_file():
            continue
        if any(part in _EXCLUDED_DIRS for part in file.relative_to(absolute).parts[:-1]):
            continue
        digest.update(file.relative_to(absolute).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(file.read_bytes())
    version = _read_project_version(absolute)
    return ResolvedSource(
        kind="local",
        location=str(absolute),
        version=version,
        commit=None,
        content_hash=digest.hexdigest(),
    )


def _read_project_version(directory: Path) -> str | None:
    pyproject = directory / "pyproject.toml"
    if not pyproject.is_file():
        return None
    for line in pyproject.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("version"):
            _, _, value = stripped.partition("=")
            return value.strip().strip('"').strip("'") or None
    return None


def _resolve_git(spec: PackageSpec, run: CommandRunner) -> ResolvedSource:
    rev = spec.rev or "HEAD"
    try:
        output = run(("git", "ls-remote", spec.location, rev))
    except OfflineResolutionError:
        raise
    except Exception as error:
        raise OfflineResolutionError(f"git resolution failed: {error}") from error
    commit = output.split("\t", 1)[0].strip() if output.strip() else ""
    if not commit:
        raise PackageResolutionError(f"git ref {rev!r} did not resolve for {spec.location}")
    if spec.rev is not None and is_pinned_commit(spec.rev) and spec.rev != commit:
        raise RefDriftError(f"ref drift: pinned {spec.rev} but remote resolves to {commit}")
    content_hash = hashlib.sha256(f"{spec.location}\n{commit}".encode()).hexdigest()
    return ResolvedSource(
        kind="git",
        location=spec.location,
        version=None,
        commit=commit,
        content_hash=content_hash,
    )


__all__ = [
    "CommandRunner",
    "OfflineResolutionError",
    "PackageResolutionError",
    "RefDriftError",
    "ResolvedSource",
    "resolve_source",
]
