from __future__ import annotations

import unittest
from pathlib import Path

THREAT_MODEL = Path(__file__).parents[1] / "docs" / "security" / "threat-model.md"
RECOVERY_TEXT = "Tool execution state is unknown after session recovery; the tool was not replayed."


class SecurityBaselineTests(unittest.TestCase):
    def test_threat_model_covers_every_frozen_trust_boundary(self) -> None:
        text = THREAT_MODEL.read_text(encoding="utf-8")

        for required_term in (
            "API key",
            "本地文件",
            "Shell",
            "模型输出",
            "项目资源",
            "Extension",
            "Session",
            "远程",
            "STRIDE",
            "DoS",
            "供应链",
            "测试",
        ):
            self.assertIn(required_term, text)
        self.assertIn(RECOVERY_TEXT, text)
