from __future__ import annotations

import unittest
from pathlib import Path

CONTRACT = Path(__file__).parents[1] / "docs" / "contracts" / "errors-exit-codes.md"


class ErrorContractTests(unittest.TestCase):
    def test_exit_codes_and_controlled_key_output_are_frozen(self) -> None:
        text = CONTRACT.read_text(encoding="utf-8")

        for code in ("`0`", "`1`", "`2`", "`130`"):
            self.assertIn(code, text)
        self.assertIn("专用 `auth print-api-key`", text)
