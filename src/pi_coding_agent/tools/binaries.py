"""Pinned, hash-verified management for ripgrep and fd binaries."""

from __future__ import annotations

import asyncio
import hashlib
import io
import os
import platform as host_platform
import shutil
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal, Protocol

type ToolName = Literal["rg", "fd"]
type AssetKey = tuple[str, str, str]
type Which = Callable[[str], str | None]

MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024


class BinaryManagerError(RuntimeError):
    pass


class Downloader(Protocol):
    async def download(self, url: str) -> bytes: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class AssetSpec:
    tool: str
    version: str
    asset_name: str
    sha256: str
    url: str
    binary_name: str


def _asset(
    tool: str,
    version: str,
    asset_name: str,
    sha256: str,
    *,
    tag: str,
    repository: str,
) -> AssetSpec:
    binary_name = f"{tool}.exe" if "windows" in asset_name else tool
    return AssetSpec(
        tool=tool,
        version=version,
        asset_name=asset_name,
        sha256=sha256,
        url=f"https://github.com/{repository}/releases/download/{tag}/{asset_name}",
        binary_name=binary_name,
    )


PINNED_ASSETS: Mapping[AssetKey, AssetSpec] = {
    ("rg", "win32", "x86_64"): _asset(
        "rg",
        "15.2.0",
        "ripgrep-15.2.0-x86_64-pc-windows-msvc.zip",
        "71b2fef860abe467217a538ff31de02f5258807c0129f771846f87bd029aafc5",
        tag="15.2.0",
        repository="BurntSushi/ripgrep",
    ),
    ("rg", "win32", "aarch64"): _asset(
        "rg",
        "15.2.0",
        "ripgrep-15.2.0-aarch64-pc-windows-msvc.zip",
        "e4abca10c3a64ebea742667dd7009449d49403db5460dd6873e389fa2945360f",
        tag="15.2.0",
        repository="BurntSushi/ripgrep",
    ),
    ("rg", "linux", "x86_64"): _asset(
        "rg",
        "15.2.0",
        "ripgrep-15.2.0-x86_64-unknown-linux-musl.tar.gz",
        "33e15bcf1624b25cdd2a55813a47a2f95dbe126268203e76aa6a585d1e7b149c",
        tag="15.2.0",
        repository="BurntSushi/ripgrep",
    ),
    ("rg", "linux", "aarch64"): _asset(
        "rg",
        "15.2.0",
        "ripgrep-15.2.0-aarch64-unknown-linux-gnu.tar.gz",
        "a740b91c82eaf9914cfedd353572f2791cbe0162c84101ee0951058f4dcbc90d",
        tag="15.2.0",
        repository="BurntSushi/ripgrep",
    ),
    ("fd", "win32", "x86_64"): _asset(
        "fd",
        "10.4.2",
        "fd-v10.4.2-x86_64-pc-windows-msvc.zip",
        "b2816e506390a89941c63c9187d58a3cc10e9a55f2ef0685f9ea0eccaf7c98c8",
        tag="v10.4.2",
        repository="sharkdp/fd",
    ),
    ("fd", "win32", "aarch64"): _asset(
        "fd",
        "10.4.2",
        "fd-v10.4.2-aarch64-pc-windows-msvc.zip",
        "4f9110c2d5b33a7f760bfa5510f4c113d828109f7277d421b1053a9943c0fc92",
        tag="v10.4.2",
        repository="sharkdp/fd",
    ),
    ("fd", "linux", "x86_64"): _asset(
        "fd",
        "10.4.2",
        "fd-v10.4.2-x86_64-unknown-linux-gnu.tar.gz",
        "def59805cd14b5651b68990855f426ad087f3b96881296d963910431ba3143c8",
        tag="v10.4.2",
        repository="sharkdp/fd",
    ),
    ("fd", "linux", "aarch64"): _asset(
        "fd",
        "10.4.2",
        "fd-v10.4.2-aarch64-unknown-linux-gnu.tar.gz",
        "6c51f7c5446b3338b1e401ff15dc194c590bb2fa64fd43ff3278300f073adec5",
        tag="v10.4.2",
        repository="sharkdp/fd",
    ),
}


class HttpDownloader:
    async def download(self, url: str) -> bytes:
        return await asyncio.to_thread(self._download, url)

    def _download(self, url: str) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": "pi-python"})
        with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
            declared = response.headers.get("Content-Length")
            if declared is not None and int(declared) > MAX_DOWNLOAD_BYTES:
                raise BinaryManagerError("Search binary archive exceeds download size limit")
            data = response.read(MAX_DOWNLOAD_BYTES + 1)
        if len(data) > MAX_DOWNLOAD_BYTES:
            raise BinaryManagerError("Search binary archive exceeds download size limit")
        return data


def _architecture(value: str) -> str:
    normalized = value.lower()
    if normalized in {"amd64", "x86_64"}:
        return "x86_64"
    if normalized in {"arm64", "aarch64"}:
        return "aarch64"
    return normalized


def _extract_binary(archive: bytes, spec: AssetSpec) -> bytes:
    expected = spec.binary_name
    if spec.asset_name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(archive)) as compressed:
            matches = [
                name
                for name in compressed.namelist()
                if not name.endswith("/") and PurePosixPath(name).name == expected
            ]
            if len(matches) != 1:
                raise BinaryManagerError(f"Archive must contain exactly one {expected}")
            return compressed.read(matches[0])
    if spec.asset_name.endswith(".tar.gz"):
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as compressed:
            matches = [
                member
                for member in compressed.getmembers()
                if member.isfile() and PurePosixPath(member.name).name == expected
            ]
            if len(matches) != 1:
                raise BinaryManagerError(f"Archive must contain exactly one {expected}")
            stream = compressed.extractfile(matches[0])
            if stream is None:
                raise BinaryManagerError(f"Could not read {expected} from archive")
            return stream.read()
    raise BinaryManagerError(f"Unsupported archive format: {spec.asset_name}")


def _atomic_install(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if sys.platform != "win32":
            temporary.chmod(0o755)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class BinaryManager:
    def __init__(
        self,
        *,
        cache_dir: Path,
        offline: bool = False,
        platform: str | None = None,
        architecture: str | None = None,
        which: Which = shutil.which,
        downloader: Downloader | None = None,
        assets: Mapping[AssetKey, AssetSpec] = PINNED_ASSETS,
    ) -> None:
        self._cache_dir = cache_dir
        self._offline = offline
        self._platform = sys.platform if platform is None else platform
        machine = host_platform.machine() if architecture is None else architecture
        self._architecture = _architecture(machine)
        self._which = which
        self._downloader = HttpDownloader() if downloader is None else downloader
        self._assets = assets
        self._locks: dict[ToolName, asyncio.Lock] = {}

    async def resolve(self, tool: ToolName) -> Path:
        names = ("fd", "fdfind") if tool == "fd" else ("rg",)
        for name in names:
            system_path = self._which(name)
            if system_path is not None:
                return Path(system_path)

        spec = self._assets.get((tool, self._platform, self._architecture))
        if spec is None:
            raise BinaryManagerError(
                f"Unsupported search binary target: {self._platform}/{self._architecture}"
            )
        cached = self._cache_dir / spec.binary_name
        if cached.is_file():
            return cached
        if self._offline:
            raise BinaryManagerError(
                f"{tool} is unavailable in offline mode; install it on PATH or populate the cache"
            )

        lock = self._locks.setdefault(tool, asyncio.Lock())
        async with lock:
            if cached.is_file():
                return cached
            try:
                archive = await self._downloader.download(spec.url)
            except BinaryManagerError:
                raise
            except OSError as error:
                raise BinaryManagerError(f"Could not download {tool}: {error}") from None
            digest = hashlib.sha256(archive).hexdigest()
            if digest != spec.sha256:
                raise BinaryManagerError(
                    f"SHA-256 mismatch for {spec.asset_name}: expected {spec.sha256}, got {digest}"
                )
            try:
                binary = await asyncio.to_thread(_extract_binary, archive, spec)
            except BinaryManagerError:
                raise
            except (OSError, tarfile.TarError, zipfile.BadZipFile, EOFError) as error:
                raise BinaryManagerError(f"Could not extract {spec.asset_name}: {error}") from None
            await asyncio.to_thread(_atomic_install, cached, binary)
            return cached


__all__ = [
    "AssetSpec",
    "BinaryManager",
    "BinaryManagerError",
    "Downloader",
    "PINNED_ASSETS",
]
