"""Ingest npm packages as pure data resources, never executing their scripts."""

from __future__ import annotations

import hashlib
import subprocess
import tarfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

ALLOWED_RESOURCE_DIRS = ("skills", "prompts", "themes")
_FORBIDDEN_SUFFIXES = (".ts", ".mts", ".cts", ".exe", ".bat", ".cmd", ".sh")


class NpmDataError(RuntimeError):
    """Base error for npm data ingestion."""


class NpmDataForbiddenError(NpmDataError):
    """The package contains scripts, code entries, or unsafe paths."""


class NpmOfflineError(NpmDataError):
    """Fetching the package requires the network but failed."""


type NpmPackRunner = Callable[[str, Path], Path]


@dataclass(frozen=True, slots=True)
class NpmDataExtraction:
    name: str
    version: str
    data_dir: Path
    files: tuple[str, ...]
    content_hash: str


def build_tarball(
    spec: str,
    *,
    cache_dir: Path,
    runner: NpmPackRunner | None = None,
) -> Path:
    pack = runner if runner is not None else _npm_pack
    cache_dir.mkdir(parents=True, exist_ok=True)
    try:
        return pack(spec, cache_dir)
    except NpmOfflineError:
        raise
    except Exception as error:
        raise NpmOfflineError(f"npm pack failed for {spec!r}: {error}") from error


def extract_npm_data(tarball: Path, dest: Path) -> NpmDataExtraction:
    content_hash = hashlib.sha256(tarball.read_bytes()).hexdigest()
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tarball, mode="r:gz") as archive:
        manifest = _read_manifest(archive)
        name = str(manifest.get("name", ""))
        version = str(manifest.get("version", ""))
        scripts = manifest.get("scripts")
        if isinstance(scripts, dict) and scripts:
            raise NpmDataForbiddenError(f"{name}: lifecycle scripts are forbidden in data packages")
        extracted: list[str] = []
        for member in archive.getmembers():
            if not member.isfile():
                continue
            if member.name.endswith(_FORBIDDEN_SUFFIXES):
                raise NpmDataForbiddenError(
                    f"executable or code file in data package: {member.name}"
                )
            relative = _relative_data_path(member.name)
            if relative is None:
                continue
            target = dest / relative
            if not target.resolve().is_relative_to(dest.resolve()):
                raise NpmDataForbiddenError(f"unsafe path in package: {member.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                continue
            target.write_bytes(source.read())
            extracted.append(relative)
        return NpmDataExtraction(
            name=name,
            version=version,
            data_dir=dest,
            files=tuple(sorted(extracted)),
            content_hash=content_hash,
        )


def _read_manifest(archive: tarfile.TarFile) -> dict[str, object]:
    import json

    member_name = "package/package.json"
    member = next((item for item in archive.getmembers() if item.name == member_name), None)
    if member is None:
        raise NpmDataForbiddenError("package.json is missing from the npm tarball")
    stream = archive.extractfile(member)
    if stream is None:
        raise NpmDataForbiddenError("package.json is unreadable")
    payload: object = json.loads(stream.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise NpmDataForbiddenError("package.json must be an object")
    return cast("dict[str, object]", payload)


def _relative_data_path(member_name: str) -> str | None:
    if member_name.startswith("../") or "/../" in member_name:
        raise NpmDataForbiddenError(f"unsafe path in package: {member_name}")
    parts = member_name.split("/")
    if len(parts) < 2 or parts[0] != "package":
        return None
    relative = "/".join(parts[1:])
    top = relative.split("/", 1)[0]
    if top not in ALLOWED_RESOURCE_DIRS:
        return None
    return relative


def _npm_pack(spec: str, cache_dir: Path) -> Path:
    completed = subprocess.run(
        ["npm", "pack", "--ignore-scripts", "--pack-destination", str(cache_dir), spec],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "npm pack failed")
    produced = sorted(cache_dir.glob("*.tgz"))
    if not produced:
        raise RuntimeError("npm pack produced no tarball")
    return produced[-1]


__all__ = [
    "ALLOWED_RESOURCE_DIRS",
    "NpmDataExtraction",
    "NpmDataError",
    "NpmDataForbiddenError",
    "NpmOfflineError",
    "build_tarball",
    "extract_npm_data",
]
