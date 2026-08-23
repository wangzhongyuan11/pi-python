from __future__ import annotations

from pathlib import Path

from scripts.verify_checkpoint import project_version

ROOT = Path(__file__).parents[2]


def test_phase_three_checkpoint_version_and_changelog_are_aligned() -> None:
    assert project_version(ROOT / "pyproject.toml") == "0.1.0"
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## 0.1.0" in changelog
