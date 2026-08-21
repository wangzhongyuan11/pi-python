from __future__ import annotations

import unittest
from pathlib import Path

CONTRACT = Path(__file__).parents[1] / "docs" / "contracts" / "session-v3.md"
RECOVERY_TEXT = "Tool execution state is unknown after session recovery; the tool was not replayed."


class SessionContractTests(unittest.TestCase):
    def test_v3_version_and_recovery_behavior_are_frozen(self) -> None:
        text = CONTRACT.read_text(encoding="utf-8")

        self.assertIn("普通 entry 不增加 `version` 或 `schemaVersion`", text)
        self.assertIn(RECOVERY_TEXT, text)

    def test_explicit_pi_import_is_read_only(self) -> None:
        text = CONTRACT.read_text(encoding="utf-8")

        self.assertIn("`import-pi-session`", text)
        self.assertIn("只读读取 `.pi` 来源", text)
