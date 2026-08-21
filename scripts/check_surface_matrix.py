"""Validate the compatibility matrix structure and optional upstream evidence."""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

CLASSIFICATIONS = frozenset({"Supported", "Intentional divergence", "Post-v1"})
ID_PATTERN = re.compile(r"^[A-Z0-9]+(?:-[A-Z0-9]+)+$")
OWNER_PHASE_PATTERN = re.compile(r"^`pi_[a-z0-9_.]+`\s*/\s*(?:P\d+(?:,P?\d+)*|Post-v1)$")
UPSTREAM_EVIDENCE_PATTERN = re.compile(r"^(packages/[^:]+):L(.+)$")
LINE_RANGE_PATTERN = re.compile(r"^L?(\d+)(?:-L?(\d+))?$")
REQUIRED_SURFACE_MARKERS = (
    "readStoredCredential",
    "import-pi-session",
    "--credentials",
    "--min-expiry",
    "Kitty",
    "LaTeX",
    "fuzzy",
)


class SurfaceMatrixError(RuntimeError):
    """Raised when the compatibility surface is incomplete or malformed."""


@dataclass(frozen=True, slots=True)
class SurfaceRow:
    identifier: str
    surface: str
    classification: str
    semantics: str
    evidence: str
    owner_phase: str
    line_number: int


def _split_markdown_row(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        raise SurfaceMatrixError("table row must start and end with '|'")

    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for character in stripped[1:-1]:
        if escaped:
            current.append("\\")
            current.append(character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(character)
    if escaped:
        current.append("\\")
    cells.append("".join(current).strip())
    return cells


def _plain_identifier(value: str) -> str:
    if len(value) >= 2 and value.startswith("`") and value.endswith("`"):
        return value[1:-1]
    return value


def parse_surface_rows(matrix: Path) -> list[SurfaceRow]:
    rows: list[SurfaceRow] = []
    in_surface_table = False

    for line_number, line in enumerate(matrix.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.lstrip().startswith("|"):
            in_surface_table = False
            continue

        cells = _split_markdown_row(line)
        if cells and cells[0] == "ID":
            if len(cells) != 6:
                raise SurfaceMatrixError(
                    f"{matrix}:{line_number}: surface header must have exactly 6 columns"
                )
            in_surface_table = True
            continue
        if not in_surface_table or all(set(cell) <= {"-", ":"} for cell in cells):
            continue
        if len(cells) != 6:
            raise SurfaceMatrixError(
                f"{matrix}:{line_number}: expected 6 columns, found {len(cells)}; "
                "escape literal pipes as \\|"
            )

        identifier = _plain_identifier(cells[0])
        rows.append(
            SurfaceRow(
                identifier=identifier,
                surface=cells[1],
                classification=cells[2],
                semantics=cells[3],
                evidence=cells[4],
                owner_phase=cells[5],
                line_number=line_number,
            )
        )
    return rows


def _evidence_tokens(row: SurfaceRow) -> list[str]:
    return re.findall(r"`([^`]+)`", row.evidence)


def _validate_row_structure(matrix: Path, rows: list[SurfaceRow]) -> None:
    if len(rows) < 200:
        raise SurfaceMatrixError(
            f"{matrix}: expected at least 200 itemized surfaces, found {len(rows)}"
        )

    seen: dict[str, int] = {}
    for row in rows:
        location = f"{matrix}:{row.line_number}"
        if ID_PATTERN.fullmatch(row.identifier) is None:
            raise SurfaceMatrixError(f"{location}: invalid surface ID {row.identifier!r}")
        if row.identifier in seen:
            raise SurfaceMatrixError(
                f"{location}: duplicate surface ID {row.identifier!r}; first at line "
                f"{seen[row.identifier]}"
            )
        seen[row.identifier] = row.line_number
        if row.classification not in CLASSIFICATIONS:
            raise SurfaceMatrixError(f"{location}: invalid classification {row.classification!r}")
        if OWNER_PHASE_PATTERN.fullmatch(row.owner_phase) is None:
            raise SurfaceMatrixError(f"{location}: invalid owner/phase {row.owner_phase!r}")

        tokens = _evidence_tokens(row)
        if not any(token.startswith(("packages/", "docs/")) for token in tokens):
            raise SurfaceMatrixError(f"{location}: evidence must cite an upstream or local file")

    classifications = {row.classification for row in rows}
    if classifications != set(CLASSIFICATIONS):
        missing = sorted(CLASSIFICATIONS - classifications)
        raise SurfaceMatrixError(f"{matrix}: missing classifications: {missing}")

    text = matrix.read_text(encoding="utf-8")
    missing_markers = [marker for marker in REQUIRED_SURFACE_MARKERS if marker not in text]
    if missing_markers:
        raise SurfaceMatrixError(f"{matrix}: missing required surfaces: {missing_markers}")


def _parse_line_ranges(location: str, raw_ranges: str) -> list[tuple[int, int]]:
    parsed: list[tuple[int, int]] = []
    for raw_range in raw_ranges.split(","):
        match = LINE_RANGE_PATTERN.fullmatch(raw_range.strip())
        if match is None:
            raise SurfaceMatrixError(f"{location}: invalid evidence line range {raw_range!r}")
        start = int(match.group(1))
        end = int(match.group(2) or match.group(1))
        if start < 1 or end < start:
            raise SurfaceMatrixError(f"{location}: invalid evidence line range {raw_range!r}")
        parsed.append((start, end))
    return parsed


def _validate_evidence_paths(
    project_root: Path,
    source: Path | None,
    matrix: Path,
    rows: list[SurfaceRow],
) -> None:
    line_counts: dict[Path, int] = {}
    for row in rows:
        location = f"{matrix}:{row.line_number}"
        for token in _evidence_tokens(row):
            if token.startswith("docs/"):
                local_path = project_root / token.split("#", 1)[0]
                if not local_path.is_file():
                    raise SurfaceMatrixError(f"{location}: local evidence does not exist: {token}")
                continue
            if not token.startswith("packages/"):
                continue

            match = UPSTREAM_EVIDENCE_PATTERN.fullmatch(token)
            if match is None:
                raise SurfaceMatrixError(
                    f"{location}: upstream evidence needs a full path and line range: {token}"
                )
            relative_path, raw_ranges = match.groups()
            parsed_ranges = _parse_line_ranges(location, raw_ranges)
            if source is None:
                continue

            evidence_path = source / Path(relative_path)
            if not evidence_path.is_file():
                raise SurfaceMatrixError(
                    f"{location}: upstream evidence does not exist: {relative_path}"
                )
            if evidence_path not in line_counts:
                line_counts[evidence_path] = len(
                    evidence_path.read_text(encoding="utf-8", errors="replace").splitlines()
                )
            line_count = line_counts[evidence_path]
            for start, end in parsed_ranges:
                if end > line_count:
                    raise SurfaceMatrixError(
                        f"{location}: evidence {relative_path}:L{start}-L{end} exceeds "
                        f"{line_count} lines"
                    )


def validate_surface_matrix(
    matrix: Path,
    *,
    project_root: Path,
    source: Path | None = None,
) -> list[SurfaceRow]:
    rows = parse_surface_rows(matrix)
    _validate_row_structure(matrix, rows)
    _validate_evidence_paths(project_root, source, matrix, rows)
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--matrix",
        type=Path,
        default=project_root / "docs" / "compatibility" / "surface-matrix.md",
    )
    parser.add_argument("--source", type=Path, help="optional frozen TypeScript source tree")
    arguments = parser.parse_args(argv)

    rows = validate_surface_matrix(
        arguments.matrix.resolve(),
        project_root=project_root,
        source=arguments.source.resolve() if arguments.source is not None else None,
    )
    print(f"validated {len(rows)} compatibility surfaces")
    return 0


def _entrypoint() -> None:
    try:
        raise SystemExit(main())
    except (OSError, SurfaceMatrixError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from None


if __name__ == "__main__":
    _entrypoint()
