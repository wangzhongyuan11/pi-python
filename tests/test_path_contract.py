from __future__ import annotations

import unittest
from pathlib import Path

CONTRACT = Path(__file__).parents[1] / "docs" / "contracts" / "paths-naming.md"


class PathContractTests(unittest.TestCase):
    def test_credential_precedence_and_cwd_dotenv_are_frozen(self) -> None:
        text = CONTRACT.read_text(encoding="utf-8")

        self.assertIn("--api-key", text)
        self.assertIn("--env-file", text)
        self.assertIn("<final runtime cwd>/.env", text)
