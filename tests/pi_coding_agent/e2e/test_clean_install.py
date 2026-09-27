"""Clean functional installation acceptance (P16-T05).

The pure verifier guards run in every test pass; the full wheel build and
functional verification runs outside the offline test gate via
``uv build --no-sources && uv run --frozen python scripts/verify_wheel.py``
or by pointing ``PI_PYTHON_VERIFY_WHEEL`` at a built wheel.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.verify_wheel import WheelVerificationError, assert_clean_output, verify_wheel

REPO = Path(__file__).resolve().parents[3]


def test_verify_wheel_requires_the_artifact(tmp_path: Path) -> None:
    with pytest.raises(WheelVerificationError, match="wheel not found"):
        verify_wheel(REPO, tmp_path / "missing.whl")


def test_probe_output_must_not_leak_the_checkout_or_tracebacks() -> None:
    assert_clean_output("pi-python 0.5.0\ncredential error\n")
    with pytest.raises(WheelVerificationError, match="leaked"):
        assert_clean_output("editable path D:\\pi-python-claude\\src\\pi_coding_agent\n")
    with pytest.raises(WheelVerificationError, match="traceback"):
        assert_clean_output("Traceback (most recent call last): ...")


def test_full_wheel_verification_runs_when_a_wheel_is_provided() -> None:
    wheel = os.environ.get("PI_PYTHON_VERIFY_WHEEL")
    if not wheel:
        pytest.skip(
            "set PI_PYTHON_VERIFY_WHEEL to a built wheel, or run "
            "`uv build --no-sources && uv run --frozen python scripts/verify_wheel.py`"
        )
    verify_wheel(REPO, wheel)
