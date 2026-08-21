from __future__ import annotations

import ast
from pathlib import Path

import pytest

SOURCE_ROOT = Path(__file__).parents[1] / "src"
PACKAGE_NAMES = frozenset({"pi_telemetry", "pi_ai", "pi_agent", "pi_tui", "pi_coding_agent"})
ALLOWED_INTERNAL_IMPORTS: dict[str, frozenset[str]] = {
    "pi_telemetry": frozenset(),
    "pi_ai": frozenset({"pi_telemetry"}),
    "pi_agent": frozenset({"pi_telemetry", "pi_ai"}),
    "pi_tui": frozenset(),
    "pi_coding_agent": frozenset({"pi_telemetry", "pi_ai", "pi_agent", "pi_tui"}),
}


def _internal_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.partition(".")[0])

    return imported & PACKAGE_NAMES


@pytest.mark.parametrize("package", sorted(PACKAGE_NAMES))
def test_internal_imports_follow_dependency_direction(package: str) -> None:
    package_root = SOURCE_ROOT / package
    assert package_root.is_dir(), f"missing package: {package}"

    forbidden_imports: list[str] = []
    for module in package_root.rglob("*.py"):
        disallowed = _internal_imports(module) - ALLOWED_INTERNAL_IMPORTS[package]
        forbidden_imports.extend(
            f"{module.relative_to(SOURCE_ROOT)} -> {name}" for name in disallowed
        )

    assert not forbidden_imports, "forbidden internal imports:\n" + "\n".join(forbidden_imports)


def test_pi_tui_does_not_import_ai_or_agent() -> None:
    tui_root = SOURCE_ROOT / "pi_tui"
    assert tui_root.is_dir(), "missing package: pi_tui"

    imports = {
        imported for module in tui_root.rglob("*.py") for imported in _internal_imports(module)
    }

    assert imports.isdisjoint({"pi_ai", "pi_agent"})
