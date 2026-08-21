from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.check_surface_matrix import (
    SurfaceMatrixError,
    parse_surface_rows,
    validate_surface_matrix,
)

PROJECT_ROOT = Path(__file__).parents[1]
MATRIX = PROJECT_ROOT / "docs" / "compatibility" / "surface-matrix.md"


class SurfaceMatrixTests(unittest.TestCase):
    def test_repository_matrix_has_itemized_ids_and_complete_metadata(self) -> None:
        rows = validate_surface_matrix(MATRIX, project_root=PROJECT_ROOT)

        self.assertGreaterEqual(len(rows), 200)
        self.assertEqual(len(rows), len({row.identifier for row in rows}))

    def test_literal_pipe_must_be_escaped_to_keep_six_columns(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            matrix = Path(directory) / "matrix.md"
            matrix.write_text(
                "| ID | Surface | Status | Semantics | Evidence | Owner |\n"
                "|---|---|---|---|---|---|\n"
                "| `CLI-001` | `--mode text|json` | Supported | local | "
                "`packages/example.ts:L1` | `pi_ai` / P1 |\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(SurfaceMatrixError, "escape literal pipes"):
                parse_surface_rows(matrix)

    def test_duplicate_surface_id_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            docs = root / "docs"
            docs.mkdir()
            (docs / "decision.md").write_text("decision\n", encoding="utf-8")
            matrix = root / "matrix.md"
            rows = "".join(
                "| `TEST-{identifier:03d}` | behavior | {classification} | semantics | "
                "`docs/decision.md` | `pi_ai` / P1 |\n".format(
                    identifier=index,
                    classification={
                        1: "Intentional divergence",
                        2: "Post-v1",
                    }.get(index, "Supported"),
                )
                for index in range(199)
            )
            duplicate = (
                "| `TEST-000` | duplicate | Supported | semantics | "
                "`docs/decision.md` | `pi_ai` / P1 |\n"
            )
            matrix.write_text(
                "| ID | Surface | Status | Semantics | Evidence | Owner |\n"
                "|---|---|---|---|---|---|\n" + rows + duplicate,
                encoding="utf-8",
            )

            with self.assertRaisesRegex(SurfaceMatrixError, "duplicate surface ID"):
                validate_surface_matrix(matrix, project_root=root)


if __name__ == "__main__":
    unittest.main()
