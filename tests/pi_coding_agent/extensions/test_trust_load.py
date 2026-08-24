from __future__ import annotations

import json
from pathlib import Path

import pytest

from pi_coding_agent.extensions.loader import (
    ExtensionLoader,
    ExtensionNotTrustedError,
    discover_extensions,
)
from pi_coding_agent.extensions.metadata import ExtensionManifestError, read_manifest

STAMP = "2026-08-24T00:00:00.000Z"


def _write_extension(root: Path, name: str, marker: Path) -> Path:
    extension_dir = root / name
    extension_dir.mkdir(parents=True)
    manifest = {"name": name, "version": "1.0.0", "entry": "main.py"}
    (extension_dir / "pi-extension.json").write_text(json.dumps(manifest), encoding="utf-8")
    (extension_dir / "main.py").write_text(
        "import pathlib\n"
        f"marker = pathlib.Path({str(marker)!r})\n"
        "with marker.open('a', encoding='utf-8') as handle:\n"
        f"    handle.write('{name}\\n')\n",
        encoding="utf-8",
    )
    return extension_dir


def test_discover_reads_manifests_without_importing_any_code(tmp_path: Path) -> None:
    marker = tmp_path / "marker.txt"
    _write_extension(tmp_path / "extensions", "side-effect", marker)

    discovered = discover_extensions(tmp_path / "extensions")

    assert [item.name for item in discovered] == ["side-effect"]
    assert not marker.exists()


def test_read_manifest_rejects_missing_fields_and_unknown_files(tmp_path: Path) -> None:
    bad = tmp_path / "broken"
    bad.mkdir()
    (bad / "pi-extension.json").write_text(json.dumps({"name": "x"}), encoding="utf-8")

    with pytest.raises(ExtensionManifestError):
        read_manifest(bad)
    with pytest.raises(ExtensionManifestError):
        read_manifest(tmp_path / "missing")


def test_load_imports_exactly_once_only_after_trust(tmp_path: Path) -> None:
    marker = tmp_path / "marker.txt"
    extension_dir = _write_extension(tmp_path / "extensions", "counted", marker)
    metadata = read_manifest(extension_dir)

    loader = ExtensionLoader()
    with pytest.raises(ExtensionNotTrustedError):
        loader.load(metadata)
    assert not marker.exists()

    loader.grant_trust(metadata.name)
    first = loader.load(metadata)
    second = loader.load(metadata)

    assert first is not None and second is first
    assert marker.read_text(encoding="utf-8") == "counted\n"


def test_discover_skips_directories_without_valid_manifests(tmp_path: Path) -> None:
    extensions = tmp_path / "extensions"
    _write_extension(extensions, "valid", tmp_path / "marker.txt")
    stray = extensions / "notes"
    stray.mkdir()
    (stray / "readme.md").write_text("not an extension", encoding="utf-8")

    assert [item.name for item in discover_extensions(extensions)] == ["valid"]
