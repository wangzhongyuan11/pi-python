from __future__ import annotations

import json
import sys
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

    loader.grant_trust(metadata)
    first = loader.load(metadata)
    second = loader.load(metadata)

    assert first is not None and second is first
    assert marker.read_text(encoding="utf-8") == "counted\n"


def test_trust_is_bound_to_extension_path_not_reused_by_name(tmp_path: Path) -> None:
    trusted_marker = tmp_path / "trusted.txt"
    swapped_marker = tmp_path / "swapped.txt"
    trusted_dir = _write_extension(tmp_path / "trusted", "same-name", trusted_marker)
    swapped_dir = _write_extension(tmp_path / "swapped", "same-name", swapped_marker)
    loader = ExtensionLoader()
    loader.grant_trust(read_manifest(trusted_dir))

    with pytest.raises(ExtensionNotTrustedError):
        loader.load(read_manifest(swapped_dir))

    assert not swapped_marker.exists()


def test_entry_change_after_trust_requires_new_approval(tmp_path: Path) -> None:
    marker = tmp_path / "marker.txt"
    extension_dir = _write_extension(tmp_path / "extensions", "mutable", marker)
    metadata = read_manifest(extension_dir)
    loader = ExtensionLoader()
    loader.grant_trust(metadata)
    (extension_dir / "main.py").write_text("raise RuntimeError('changed')\n", encoding="utf-8")

    with pytest.raises(ExtensionNotTrustedError):
        loader.load(metadata)

    assert not marker.exists()


def test_manifest_rejects_entry_outside_extension_directory(tmp_path: Path) -> None:
    extension_dir = tmp_path / "extension"
    extension_dir.mkdir()
    (extension_dir / "pi-extension.json").write_text(
        json.dumps({"name": "escape", "version": "1.0.0", "entry": "../outside.py"}),
        encoding="utf-8",
    )

    with pytest.raises(ExtensionManifestError):
        read_manifest(extension_dir)


def test_failed_import_does_not_leave_module_in_global_cache(tmp_path: Path) -> None:
    marker = tmp_path / "marker.txt"
    extension_dir = _write_extension(tmp_path / "extensions", "broken", marker)
    (extension_dir / "main.py").write_text("raise RuntimeError('broken')\n", encoding="utf-8")
    metadata = read_manifest(extension_dir)
    loader = ExtensionLoader()
    loader.grant_trust(metadata)
    before = {name for name in sys.modules if name.startswith("pi_extension_")}

    with pytest.raises(RuntimeError, match="broken"):
        loader.load(metadata)

    after = {name for name in sys.modules if name.startswith("pi_extension_")}
    assert after == before


def test_discover_skips_directories_without_valid_manifests(tmp_path: Path) -> None:
    extensions = tmp_path / "extensions"
    _write_extension(extensions, "valid", tmp_path / "marker.txt")
    stray = extensions / "notes"
    stray.mkdir()
    (stray / "readme.md").write_text("not an extension", encoding="utf-8")

    assert [item.name for item in discover_extensions(extensions)] == ["valid"]
