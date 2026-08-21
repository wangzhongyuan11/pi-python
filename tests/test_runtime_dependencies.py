from __future__ import annotations

import importlib.metadata
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]


def test_pydantic_is_a_pinned_runtime_dependency() -> None:
    metadata = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert metadata["project"]["dependencies"] == ["pydantic==2.13.4"]
    assert importlib.metadata.version("pydantic") == "2.13.4"
