"""Verify the structure and legal notice of built distributions."""

from __future__ import annotations

import argparse
import sys
import tarfile
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

NOTICE_NAME = "THIRD_PARTY_NOTICES.md"
PACKAGE_NAMES = (
    "pi_telemetry",
    "pi_ai",
    "pi_agent",
    "pi_tui",
    "pi_coding_agent",
)
MIT_NOTICE_MARKERS = (
    b"MIT License",
    b"Copyright (c) 2025 Mario Zechner",
    b"Permission is hereby granted, free of charge",
    b'THE SOFTWARE IS PROVIDED "AS IS"',
)


class DistributionVerificationError(RuntimeError):
    """Raised when a built distribution does not match the frozen contract."""


@dataclass(frozen=True, slots=True)
class VerifiedDistributions:
    wheel: Path
    sdist: Path
    packages: tuple[str, ...]
    wheel_notice: str
    sdist_notice: str


def find_distributions(dist_directory: Path) -> tuple[Path, Path]:
    wheels = sorted(dist_directory.glob("*.whl"))
    if len(wheels) != 1:
        raise DistributionVerificationError(
            f"expected exactly one wheel in {dist_directory}, found {len(wheels)}"
        )

    sdists = sorted(dist_directory.glob("*.tar.gz"))
    if len(sdists) != 1:
        raise DistributionVerificationError(
            f"expected exactly one source distribution in {dist_directory}, found {len(sdists)}"
        )
    return wheels[0], sdists[0]


def _validate_expected_notice(expected_notice: bytes) -> None:
    if any(marker not in expected_notice for marker in MIT_NOTICE_MARKERS):
        raise DistributionVerificationError(
            f"source {NOTICE_NAME} does not contain the complete MIT license"
        )


def _package_error(artifact: str, found: set[str]) -> DistributionVerificationError:
    missing = [package for package in PACKAGE_NAMES if package not in found]
    unexpected = sorted(found.difference(PACKAGE_NAMES))
    details: list[str] = []
    if missing:
        details.append(f"missing {', '.join(missing)}")
    if unexpected:
        details.append(f"unexpected {', '.join(unexpected)}")
    return DistributionVerificationError(
        f"{artifact} package namespaces are invalid: {'; '.join(details)}"
    )


def _verify_wheel(wheel: Path, expected_notice: bytes) -> str:
    try:
        with zipfile.ZipFile(wheel) as archive:
            names = archive.namelist()
            matches = [
                name for name in names if name.endswith(f".dist-info/licenses/{NOTICE_NAME}")
            ]
            if len(matches) != 1:
                raise DistributionVerificationError(
                    f"expected one {NOTICE_NAME} in wheel metadata, found {len(matches)}"
                )
            actual_notice = archive.read(matches[0])
    except (OSError, zipfile.BadZipFile) as exc:
        raise DistributionVerificationError(f"could not read wheel {wheel}: {exc}") from exc

    if actual_notice != expected_notice:
        raise DistributionVerificationError(f"{NOTICE_NAME} in the wheel does not match source")

    found = {
        name.split("/", 1)[0]
        for name in names
        if name.endswith("/__init__.py") and name.split("/", 1)[0].startswith("pi_")
    }
    if found != set(PACKAGE_NAMES):
        raise _package_error("wheel", found)
    return matches[0]


def _verify_sdist(sdist: Path, expected_notice: bytes) -> str:
    try:
        with tarfile.open(sdist, "r:gz") as archive:
            members = {member.name: member for member in archive.getmembers()}
            matches = [name for name in members if name.endswith(f"/{NOTICE_NAME}")]
            if len(matches) != 1:
                raise DistributionVerificationError(
                    f"expected one {NOTICE_NAME} in source distribution, found {len(matches)}"
                )
            notice_file = archive.extractfile(members[matches[0]])
            if notice_file is None:
                raise DistributionVerificationError(
                    f"{NOTICE_NAME} in the source distribution is not a regular file"
                )
            actual_notice = notice_file.read()
    except (OSError, tarfile.TarError) as exc:
        raise DistributionVerificationError(
            f"could not read source distribution {sdist}: {exc}"
        ) from exc

    if actual_notice != expected_notice:
        raise DistributionVerificationError(
            f"{NOTICE_NAME} in the source distribution does not match source"
        )

    root = matches[0].removesuffix(f"/{NOTICE_NAME}")
    src_prefix = f"{root}/src/"
    found = {
        name.removeprefix(src_prefix).split("/", 1)[0]
        for name in members
        if name.startswith(src_prefix)
        and name.endswith("/__init__.py")
        and name.removeprefix(src_prefix).split("/", 1)[0].startswith("pi_")
    }
    if found != set(PACKAGE_NAMES):
        raise _package_error("source distribution", found)
    return matches[0]


def verify_distributions(
    dist_directory: Path,
    expected_notice: bytes,
) -> VerifiedDistributions:
    _validate_expected_notice(expected_notice)
    wheel, sdist = find_distributions(dist_directory)
    wheel_notice = _verify_wheel(wheel, expected_notice)
    sdist_notice = _verify_sdist(sdist, expected_notice)
    return VerifiedDistributions(
        wheel=wheel,
        sdist=sdist,
        packages=PACKAGE_NAMES,
        wheel_notice=wheel_notice,
        sdist_notice=sdist_notice,
    )


def _read_notice(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise DistributionVerificationError(f"could not read source notice {path}: {exc}") from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    parser.add_argument("--notice", type=Path, default=Path(NOTICE_NAME))
    arguments = parser.parse_args(argv)

    result = verify_distributions(arguments.dist, _read_notice(arguments.notice))
    print(f"verified {result.wheel} and {result.sdist}")
    return 0


def _entrypoint() -> None:
    try:
        raise SystemExit(main())
    except DistributionVerificationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from None


if __name__ == "__main__":
    _entrypoint()
