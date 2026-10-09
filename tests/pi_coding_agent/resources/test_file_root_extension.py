"""Package manifests may declare a single extension FILE as a resource root."""

from __future__ import annotations

import json
from pathlib import Path

from pi_coding_agent.resources.default_loader import _collect_extensions


def _package_with_file_entry(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "package.json").write_text(
        json.dumps({"name": "real", "pi": {"extensions": ["./index.js"]}}),
        encoding="utf-8",
    )
    (root / "index.js").write_text("export default function () {}\n", encoding="utf-8")
    return root / "index.js"


def test_file_extension_root_is_reported_as_a_bridged_entry(tmp_path: Path) -> None:
    entry = _package_with_file_entry(tmp_path)

    discovered = _collect_extensions([entry], [])

    assert len(discovered) == 1
    metadata = discovered[0]
    assert metadata.name == "index"
    assert metadata.entry == "index.js"
    assert metadata.path == entry.parent


def test_directory_roots_keep_directory_semantics(tmp_path: Path) -> None:
    extension = tmp_path / "ext"
    extension.mkdir()
    (extension / "pi-extension.json").write_text(
        json.dumps({"name": "py-ext", "version": "1.0.0", "entry": "main.py"}),
        encoding="utf-8",
    )

    discovered = _collect_extensions([extension], [])

    assert len(discovered) == 1
    assert discovered[0].name == "py-ext"
    assert discovered[0].entry == "main.py"
