from __future__ import annotations

import importlib
from importlib.metadata import version

import pytest

PACKAGE_NAMES = ("pi_telemetry", "pi_ai", "pi_agent", "pi_tui", "pi_coding_agent")


@pytest.mark.parametrize("package_name", PACKAGE_NAMES)
def test_package_is_importable_with_distribution_version(package_name: str) -> None:
    package = importlib.import_module(package_name)

    assert package.__version__ == "0.5.0"
    assert package.__version__ == version("pi-python")
