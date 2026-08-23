"""Verify a checkpoint wheel from a clean, repository-external environment."""

from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
import tomllib
import zipfile
from collections.abc import Sequence
from pathlib import Path
from typing import cast


class CheckpointError(RuntimeError):
    """A checkpoint artifact is missing, inconsistent, or not installable."""


def project_version(path: str | Path) -> str:
    with Path(path).open("rb") as file:
        payload = cast("dict[str, object]", tomllib.load(file))
    project = payload.get("project")
    if not isinstance(project, dict):
        raise CheckpointError("pyproject.toml has no project table")
    version = cast("dict[str, object]", project).get("version")
    if not isinstance(version, str):
        raise CheckpointError("project.version is missing")
    return version


def _wheel(root: Path, version: str) -> Path:
    matches = sorted((root / "dist").glob(f"pi_python-{version}-*.whl"))
    if len(matches) != 1:
        raise CheckpointError(f"expected one wheel for {version}, found {len(matches)}")
    return matches[0].resolve()


def _python_path(environment: Path) -> Path:
    return environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def verify_checkpoint(root: str | Path, version: str) -> None:
    repository = Path(root).resolve()
    actual = project_version(repository / "pyproject.toml")
    if actual != version:
        raise CheckpointError(f"project version is {actual}, expected {version}")
    wheel = _wheel(repository, version)
    with zipfile.ZipFile(wheel) as archive:
        metadata_names = [
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        ]
        if len(metadata_names) != 1:
            raise CheckpointError("wheel does not contain exactly one METADATA file")
        metadata = archive.read(metadata_names[0]).decode("utf-8")
        if f"Version: {version}\n" not in metadata:
            raise CheckpointError("wheel metadata version does not match")

    with tempfile.TemporaryDirectory(prefix="pi-python-checkpoint-") as temporary_name:
        temporary = Path(temporary_name).resolve()
        environment = temporary / "venv"
        subprocess.run(
            ["uv", "venv", "--python", "3.12", str(environment)],
            cwd=temporary,
            check=True,
            capture_output=True,
            text=True,
        )
        python = _python_path(environment)
        subprocess.run(
            ["uv", "pip", "install", "--offline", "--python", str(python), str(wheel)],
            cwd=temporary,
            check=True,
            capture_output=True,
            text=True,
        )
        work = temporary / "work"
        work.mkdir()
        clean_environment = os.environ.copy()
        clean_environment.pop("PYTHONPATH", None)
        clean_environment["PYTHONNOUSERSITE"] = "1"
        probe = subprocess.run(
            [
                str(python),
                "-c",
                "import pi_ai,pi_agent,pi_coding_agent,pi_telemetry,pi_tui;"
                "print(pi_coding_agent.__version__)",
            ],
            cwd=work,
            env=clean_environment,
            check=True,
            capture_output=True,
            text=True,
        )
        if probe.stdout.strip() != version:
            raise CheckpointError("external wheel import returned the wrong version")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[1])
    arguments = parser.parse_args(argv)
    verify_checkpoint(arguments.root, arguments.version)
    print(f"checkpoint {arguments.version} verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
