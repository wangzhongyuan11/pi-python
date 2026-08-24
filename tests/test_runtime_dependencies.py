from __future__ import annotations

import importlib.metadata
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]


def test_pydantic_is_a_pinned_runtime_dependency() -> None:
    metadata = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert metadata["project"]["dependencies"] == [
        "openai==3.1.0",
        "pydantic==2.13.4",
        "prompt-toolkit==3.0.53",
        "wcwidth==0.8.2",
    ]
    assert importlib.metadata.version("pydantic") == "2.13.4"


def test_openai_is_a_pinned_importable_runtime_dependency() -> None:
    from openai import AsyncOpenAI

    assert importlib.metadata.version("openai") == "3.1.0"
    assert AsyncOpenAI.__name__ == "AsyncOpenAI"


def test_prompt_toolkit_is_a_pinned_importable_runtime_dependency() -> None:
    from prompt_toolkit import Application

    assert importlib.metadata.version("prompt-toolkit") == "3.0.53"
    assert Application.__name__ == "Application"
