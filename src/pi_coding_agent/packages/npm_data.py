"""Ingest npm packages as pure data resources, never executing their scripts."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tarfile
import tempfile
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import cast

ALLOWED_RESOURCE_DIRS = ("skills", "prompts", "themes")
MAX_TARBALL_BYTES = 20 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 2_048
MAX_MEMBER_BYTES = 5 * 1024 * 1024
MAX_EXTRACTED_BYTES = 20 * 1024 * 1024
_FORBIDDEN_SUFFIXES = (
    ".bat",
    ".cjs",
    ".cmd",
    ".com",
    ".cts",
    ".exe",
    ".js",
    ".dll",
    ".mjs",
    ".mts",
    ".ps1",
    ".py",
    ".sh",
    ".so",
    ".ts",
    ".dylib",
)
_CODE_ENTRY_FIELDS = ("bin", "browser", "exports", "main", "module")


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
        tarball = pack(spec, cache_dir)
        resolved_cache = cache_dir.resolve()
        resolved_tarball = tarball.resolve()
        if resolved_tarball.parent != resolved_cache or not resolved_tarball.is_file():
            raise NpmDataForbiddenError("npm pack returned a path outside its cache")
        return resolved_tarball
    except NpmDataError:
        raise
    except Exception as error:
        raise NpmOfflineError(f"npm pack failed for {spec!r}: {error}") from error


def extract_npm_data(tarball: Path, dest: Path) -> NpmDataExtraction:
    content_hash = _tarball_hash(tarball)
    pending: list[tuple[str, bytes]] = []
    with _open_archive(tarball) as archive:
        members = archive.getmembers()
        if len(members) > MAX_ARCHIVE_MEMBERS:
            raise NpmDataForbiddenError("npm tarball contains too many members")
        manifest = _read_manifest(archive)
        name = _manifest_string(manifest, "name")
        version = _manifest_string(manifest, "version")
        scripts = manifest.get("scripts")
        if scripts not in (None, {}):
            raise NpmDataForbiddenError(f"{name}: lifecycle scripts are forbidden in data packages")
        for field in _CODE_ENTRY_FIELDS:
            if manifest.get(field) not in (None, "", (), [], {}):
                raise NpmDataForbiddenError(f"{name}: code entry field {field!r} is forbidden")
        total_size = 0
        identities: set[str] = set()
        for member in members:
            if not member.isfile():
                continue
            if member.name.casefold().endswith(_FORBIDDEN_SUFFIXES):
                raise NpmDataForbiddenError(
                    f"executable or code file in data package: {member.name}"
                )
            relative = _relative_data_path(member.name)
            if relative is None:
                continue
            identity = relative.casefold()
            if identity in identities:
                raise NpmDataForbiddenError(f"duplicate resource path in package: {relative}")
            identities.add(identity)
            if member.size < 0 or member.size > MAX_MEMBER_BYTES:
                raise NpmDataForbiddenError(f"resource exceeds member size limit: {member.name}")
            total_size += member.size
            if total_size > MAX_EXTRACTED_BYTES:
                raise NpmDataForbiddenError("npm data extraction exceeds total size limit")
            source = archive.extractfile(member)
            if source is None:
                raise NpmDataForbiddenError(f"resource is unreadable: {member.name}")
            payload = source.read(member.size + 1)
            if len(payload) != member.size:
                raise NpmDataForbiddenError(f"resource size mismatch: {member.name}")
            pending.append((relative, payload))
    _replace_destination(dest, pending)
    return NpmDataExtraction(
        name=name,
        version=version,
        data_dir=dest,
        files=tuple(sorted(relative for relative, _payload in pending)),
        content_hash=content_hash,
    )


@contextmanager
def _open_archive(tarball: Path) -> Iterator[tarfile.TarFile]:
    try:
        with tarfile.open(tarball, mode="r:gz") as archive:
            yield archive
    except (OSError, EOFError, tarfile.TarError) as error:
        raise NpmDataForbiddenError(f"invalid npm tarball: {tarball}") from error


def _read_manifest(archive: tarfile.TarFile) -> dict[str, object]:
    member_name = "package/package.json"
    member = next((item for item in archive.getmembers() if item.name == member_name), None)
    if member is None:
        raise NpmDataForbiddenError("package.json is missing from the npm tarball")
    stream = archive.extractfile(member)
    if stream is None:
        raise NpmDataForbiddenError("package.json is unreadable")
    if member.size > MAX_MEMBER_BYTES:
        raise NpmDataForbiddenError("package.json exceeds size limit")
    try:
        payload: object = json.loads(stream.read(member.size + 1).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise NpmDataForbiddenError("package.json is invalid") from error
    if not isinstance(payload, dict):
        raise NpmDataForbiddenError("package.json must be an object")
    return cast("dict[str, object]", payload)


def _manifest_string(manifest: dict[str, object], field: str) -> str:
    value = manifest.get(field)
    if not isinstance(value, str) or not value.strip():
        raise NpmDataForbiddenError(f"package.json field {field!r} must be a non-empty string")
    return value


def _relative_data_path(member_name: str) -> str | None:
    if (
        not member_name
        or "\\" in member_name
        or member_name.startswith(("/", "../"))
        or "/../" in member_name
        or "//" in member_name
    ):
        raise NpmDataForbiddenError(f"unsafe path in package: {member_name}")
    parts = member_name.split("/")
    if len(parts) < 2 or parts[0] != "package":
        return None
    relative = "/".join(parts[1:])
    top = relative.split("/", 1)[0]
    if top not in ALLOWED_RESOURCE_DIRS:
        return None
    return relative


def _tarball_hash(tarball: Path) -> str:
    try:
        size = tarball.stat().st_size
    except OSError as error:
        raise NpmDataForbiddenError(f"npm tarball is unreadable: {tarball}") from error
    if size > MAX_TARBALL_BYTES:
        raise NpmDataForbiddenError("npm tarball exceeds size limit")
    digest = hashlib.sha256()
    try:
        with tarball.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise NpmDataForbiddenError(f"npm tarball is unreadable: {tarball}") from error
    return digest.hexdigest()


def _replace_destination(dest: Path, files: list[tuple[str, bytes]]) -> None:
    if not dest.name or dest.resolve() == dest.parent.resolve():
        raise NpmDataForbiddenError(f"unsafe npm data destination: {dest}")
    parent = dest.parent.resolve()
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{dest.name}.", suffix=".staging", dir=parent))
    backup = parent / f".{dest.name}.{uuid.uuid4().hex}.backup"
    moved_previous = False
    activated = False
    try:
        for relative, payload in files:
            target = staging / relative
            if (
                target.parent.resolve() != staging.resolve()
                and not target.parent.resolve().is_relative_to(staging.resolve())
            ):
                raise NpmDataForbiddenError(f"unsafe resource destination: {relative}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
        if _path_exists(dest):
            dest.rename(backup)
            moved_previous = True
        staging.rename(dest)
        activated = True
    except Exception:
        if activated:
            _remove_sibling(dest, parent)
        if moved_previous and _path_exists(backup):
            backup.rename(dest)
        raise
    finally:
        if _path_exists(staging):
            _remove_sibling(staging, parent)
    if moved_previous:
        _remove_sibling(backup, parent)


def _path_exists(path: Path) -> bool:
    return path.exists() or path.is_symlink() or path.is_junction()


def _remove_sibling(path: Path, parent: Path) -> None:
    if path.parent.resolve() != parent.resolve():
        raise RuntimeError(f"refusing to remove path outside npm data directory: {path}")
    if path.is_symlink() or path.is_junction() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.exists():
        shutil.rmtree(path)


def _npm_pack(spec: str, cache_dir: Path) -> Path:
    before = {
        path.name: (path.stat().st_mtime_ns, path.stat().st_size)
        for path in cache_dir.glob("*.tgz")
    }
    completed = subprocess.run(
        ["npm", "pack", "--ignore-scripts", "--pack-destination", str(cache_dir), "--", spec],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "npm pack failed")
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("npm pack produced no tarball")
    filename = lines[-1]
    if Path(filename).name != filename:
        raise RuntimeError("npm pack reported an unsafe tarball path")
    produced = cache_dir / filename
    if not produced.is_file():
        raise RuntimeError("npm pack reported a missing tarball")
    previous = before.get(filename)
    current = (produced.stat().st_mtime_ns, produced.stat().st_size)
    if previous == current:
        raise RuntimeError("npm pack did not produce a fresh tarball")
    return produced


__all__ = [
    "ALLOWED_RESOURCE_DIRS",
    "MAX_ARCHIVE_MEMBERS",
    "MAX_EXTRACTED_BYTES",
    "MAX_MEMBER_BYTES",
    "MAX_TARBALL_BYTES",
    "NpmDataExtraction",
    "NpmDataError",
    "NpmDataForbiddenError",
    "NpmOfflineError",
    "build_tarball",
    "extract_npm_data",
]
