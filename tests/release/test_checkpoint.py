from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from scripts.verify_checkpoint import CheckpointError, project_version, verify_wheel_sources

ROOT = Path(__file__).parents[2]


def test_phase_eleven_checkpoint_version_and_changelog_are_aligned() -> None:
    assert project_version(ROOT / "pyproject.toml") == "0.5.0"
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## 0.5.0" in changelog


def test_checkpoint_rejects_wheel_source_that_differs_from_checkout(tmp_path: Path) -> None:
    package = tmp_path / "src" / "pi_example"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text('VALUE = "current"\n', encoding="utf-8")
    wheel = tmp_path / "pi_python-0.3.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("pi_example/__init__.py", 'VALUE = "stale"\n')

    with pytest.raises(CheckpointError, match="does not match checkout"):
        verify_wheel_sources(tmp_path, wheel)
