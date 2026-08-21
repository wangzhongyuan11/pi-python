from __future__ import annotations

import io
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path

import pytest

from scripts.verify_distribution import (
    DistributionVerificationError,
    find_distributions,
    verify_distributions,
)

PACKAGES = (
    "pi_telemetry",
    "pi_ai",
    "pi_agent",
    "pi_tui",
    "pi_coding_agent",
)
PROJECT_ROOT = Path(__file__).parents[1]
MIT_NOTICE = b"""# Third-party notices

MIT License

Copyright (c) 2025 Mario Zechner

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the \"Software\"), to deal
in the Software without restriction.

THE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY KIND.
"""


def _write_wheel(
    path: Path,
    notice: bytes | None = MIT_NOTICE,
    *,
    packages: tuple[str, ...] = PACKAGES,
) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for package in packages:
            archive.writestr(f"{package}/__init__.py", "")
        if notice is not None:
            archive.writestr(
                "pi_python-0.0.0.dist-info/licenses/THIRD_PARTY_NOTICES.md",
                notice,
            )


def _write_sdist(
    path: Path,
    notice: bytes | None = MIT_NOTICE,
    *,
    packages: tuple[str, ...] = PACKAGES,
) -> None:
    with tarfile.open(path, "w:gz") as archive:
        members: dict[str, bytes] = {
            f"pi_python-0.0.0/src/{package}/__init__.py": b"" for package in packages
        }
        if notice is not None:
            members["pi_python-0.0.0/THIRD_PARTY_NOTICES.md"] = notice
        for name, content in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))


def _write_valid_distributions(directory: Path) -> tuple[Path, Path]:
    wheel = directory / "pi_python-0.0.0-py3-none-any.whl"
    sdist = directory / "pi_python-0.0.0.tar.gz"
    _write_wheel(wheel)
    _write_sdist(sdist)
    return wheel, sdist


@pytest.mark.parametrize("artifact", ["wheel", "sdist"])
def test_distribution_directory_requires_exactly_one_of_each_artifact(
    tmp_path: Path,
    artifact: str,
) -> None:
    wheel, sdist = _write_valid_distributions(tmp_path)
    if artifact == "wheel":
        wheel.unlink()
        expected = "exactly one wheel"
    else:
        sdist.unlink()
        expected = "exactly one source distribution"

    with pytest.raises(DistributionVerificationError, match=expected):
        find_distributions(tmp_path)


@pytest.mark.parametrize("artifact", ["wheel", "sdist"])
def test_distribution_directory_rejects_duplicate_artifacts(
    tmp_path: Path,
    artifact: str,
) -> None:
    _write_valid_distributions(tmp_path)
    if artifact == "wheel":
        _write_wheel(tmp_path / "duplicate.whl")
        expected = "exactly one wheel"
    else:
        _write_sdist(tmp_path / "duplicate.tar.gz")
        expected = "exactly one source distribution"

    with pytest.raises(DistributionVerificationError, match=expected):
        find_distributions(tmp_path)


def test_wheel_and_sdist_contain_exact_notice_and_all_namespaces(tmp_path: Path) -> None:
    wheel, sdist = _write_valid_distributions(tmp_path)

    result = verify_distributions(tmp_path, MIT_NOTICE)

    assert result.wheel == wheel
    assert result.sdist == sdist
    assert result.packages == PACKAGES


def test_distribution_metadata_declares_the_third_party_notice() -> None:
    metadata = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert metadata["project"]["license-files"] == ["THIRD_PARTY_NOTICES.md"]


@pytest.mark.parametrize("artifact", ["wheel", "sdist"])
@pytest.mark.parametrize("notice", [None, b"different notice"])
def test_missing_or_changed_notice_is_rejected(
    tmp_path: Path,
    artifact: str,
    notice: bytes | None,
) -> None:
    wheel, sdist = _write_valid_distributions(tmp_path)
    if artifact == "wheel":
        wheel.unlink()
        _write_wheel(wheel, notice)
    else:
        sdist.unlink()
        _write_sdist(sdist, notice)

    with pytest.raises(DistributionVerificationError, match="THIRD_PARTY_NOTICES.md"):
        verify_distributions(tmp_path, MIT_NOTICE)


@pytest.mark.parametrize("artifact", ["wheel", "sdist"])
def test_missing_package_namespace_is_rejected(tmp_path: Path, artifact: str) -> None:
    wheel = tmp_path / "pi_python-0.0.0-py3-none-any.whl"
    sdist = tmp_path / "pi_python-0.0.0.tar.gz"
    packages = PACKAGES[:-1]
    _write_wheel(wheel, packages=packages if artifact == "wheel" else PACKAGES)
    _write_sdist(sdist, packages=packages if artifact == "sdist" else PACKAGES)

    with pytest.raises(DistributionVerificationError, match="pi_coding_agent"):
        verify_distributions(tmp_path, MIT_NOTICE)


def test_source_notice_must_contain_complete_mit_terms(tmp_path: Path) -> None:
    _write_valid_distributions(tmp_path)

    with pytest.raises(DistributionVerificationError, match="complete MIT license"):
        verify_distributions(tmp_path, b"MIT License\n")


def test_cli_reports_verification_errors_without_a_traceback(tmp_path: Path) -> None:
    notice = tmp_path / "THIRD_PARTY_NOTICES.md"
    notice.write_bytes(MIT_NOTICE)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.verify_distribution",
            "--dist",
            str(tmp_path / "missing-dist"),
            "--notice",
            str(notice),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.startswith("error: ")
    assert "Traceback" not in result.stderr
