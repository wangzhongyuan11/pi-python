from __future__ import annotations

import asyncio
import hashlib
import io
import zipfile
from collections.abc import Callable, Mapping
from pathlib import Path

import pytest

from pi_coding_agent.tools.binaries import (
    AssetSpec,
    BinaryManager,
    BinaryManagerError,
)


class FakeDownloader:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.urls: list[str] = []

    async def download(self, url: str) -> bytes:
        self.urls.append(url)
        return self.payload


def _zip_binary(name: str, payload: bytes) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(f"nested/{name}", payload)
    return stream.getvalue()


def _spec(tool: str, archive: bytes) -> AssetSpec:
    return AssetSpec(
        tool=tool,
        version="test",
        asset_name=f"{tool}.zip",
        sha256=hashlib.sha256(archive).hexdigest(),
        url=f"https://example.invalid/{tool}.zip",
        binary_name=f"{tool}.exe",
    )


def _which(paths: Mapping[str, str]) -> Callable[[str], str | None]:
    def which(command: str) -> str | None:
        return paths.get(command)

    return which


def test_system_binary_is_preferred_over_managed_cache(tmp_path: Path) -> None:
    cached = tmp_path / "rg.exe"
    cached.write_bytes(b"cached")
    downloader = FakeDownloader(b"unused")
    manager = BinaryManager(
        cache_dir=tmp_path,
        platform="win32",
        architecture="x86_64",
        which=_which({"rg": r"C:\Tools\rg.exe"}),
        downloader=downloader,
    )

    resolved = asyncio.run(manager.resolve("rg"))

    assert resolved == Path(r"C:\Tools\rg.exe")
    assert downloader.urls == []


def test_managed_cache_is_used_without_network(tmp_path: Path) -> None:
    cached = tmp_path / "fd.exe"
    cached.write_bytes(b"cached")
    downloader = FakeDownloader(b"unused")
    manager = BinaryManager(
        cache_dir=tmp_path,
        platform="win32",
        architecture="x86_64",
        which=_which({}),
        downloader=downloader,
    )

    assert asyncio.run(manager.resolve("fd")) == cached
    assert downloader.urls == []


def test_offline_mode_never_calls_downloader(tmp_path: Path) -> None:
    downloader = FakeDownloader(b"unused")
    manager = BinaryManager(
        cache_dir=tmp_path,
        platform="win32",
        architecture="x86_64",
        offline=True,
        which=_which({}),
        downloader=downloader,
    )

    with pytest.raises(BinaryManagerError, match="offline mode"):
        asyncio.run(manager.resolve("rg"))

    assert downloader.urls == []


def test_hash_mismatch_leaves_cache_unchanged(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    archive = _zip_binary("rg.exe", b"binary")
    spec = _spec("rg", archive)
    bad_spec = AssetSpec(
        tool=spec.tool,
        version=spec.version,
        asset_name=spec.asset_name,
        sha256="0" * 64,
        url=spec.url,
        binary_name=spec.binary_name,
    )
    manager = BinaryManager(
        cache_dir=cache,
        platform="win32",
        architecture="x86_64",
        which=_which({}),
        downloader=FakeDownloader(archive),
        assets={("rg", "win32", "x86_64"): bad_spec},
    )

    with pytest.raises(BinaryManagerError, match="SHA-256 mismatch"):
        asyncio.run(manager.resolve("rg"))

    assert not cache.exists()


def test_verified_archive_installs_only_the_expected_binary(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    archive = _zip_binary("rg.exe", b"verified-binary")
    spec = _spec("rg", archive)
    downloader = FakeDownloader(archive)
    manager = BinaryManager(
        cache_dir=cache,
        platform="win32",
        architecture="x86_64",
        which=_which({}),
        downloader=downloader,
        assets={("rg", "win32", "x86_64"): spec},
    )

    resolved = asyncio.run(manager.resolve("rg"))

    assert resolved.read_bytes() == b"verified-binary"
    assert [item.name for item in cache.iterdir()] == ["rg.exe"]
    assert downloader.urls == [spec.url]


def test_malformed_verified_archive_is_a_typed_error(tmp_path: Path) -> None:
    archive = b"not-a-zip"
    spec = _spec("rg", archive)
    manager = BinaryManager(
        cache_dir=tmp_path / "cache",
        platform="win32",
        architecture="x86_64",
        which=_which({}),
        downloader=FakeDownloader(archive),
        assets={("rg", "win32", "x86_64"): spec},
    )

    with pytest.raises(BinaryManagerError, match="Could not extract"):
        asyncio.run(manager.resolve("rg"))
