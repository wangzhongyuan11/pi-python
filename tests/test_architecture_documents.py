from __future__ import annotations

import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]
DECISIONS = PROJECT_ROOT / "docs" / "decisions"
FROZEN_COMMIT = "e14afc648e10fb6c527ea88fa627091ada764306"


class ArchitectureDocumentsTests(unittest.TestCase):
    def test_architecture_decisions_freeze_source_packages_and_workflow(self) -> None:
        required = {
            "0001-source-baseline-and-scope.md",
            "0002-single-wheel-package-boundaries.md",
            "0003-compatibility-divergence-and-session-recovery.md",
            "0004-development-workflow.md",
        }
        missing = sorted(name for name in required if not (DECISIONS / name).is_file())

        self.assertFalse(missing, f"missing architecture decisions: {missing}")
        self.assertIn(
            FROZEN_COMMIT,
            (DECISIONS / "0001-source-baseline-and-scope.md").read_text(encoding="utf-8"),
        )

    def test_tui_package_is_documented_as_a_standalone_internal_boundary(self) -> None:
        text = (DECISIONS / "0002-single-wheel-package-boundaries.md").read_text(encoding="utf-8")

        self.assertIn("不导入任何其他 `pi_*` package", text)
