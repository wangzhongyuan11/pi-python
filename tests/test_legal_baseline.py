from __future__ import annotations

import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]
FROZEN_COMMIT = "e14afc648e10fb6c527ea88fa627091ada764306"


class LegalBaselineTests(unittest.TestCase):
    def test_upstream_notice_is_complete_without_a_root_project_license(self) -> None:
        notice = (PROJECT_ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")

        self.assertFalse((PROJECT_ROOT / "LICENSE").exists())
        self.assertIn(FROZEN_COMMIT, notice)
        self.assertIn("MIT License", notice)
        self.assertIn("Copyright (c) 2025 Mario Zechner", notice)
        self.assertIn('THE SOFTWARE IS PROVIDED "AS IS"', notice)
