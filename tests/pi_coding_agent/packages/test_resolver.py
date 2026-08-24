from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from pi_coding_agent.packages.resolver import (
    OfflineResolutionError,
    RefDriftError,
    resolve_source,
)
from pi_coding_agent.packages.spec import PackageSpecError, parse_package_spec


def test_parse_specs_across_kinds() -> None:
    local = parse_package_spec("./tools/kit")
    git_pinned = parse_package_spec("git+https://example.com/acme/ext.git@1a2b3c")
    pypi_pinned = parse_package_spec("acme-ext==2.0.0")
    pypi_loose = parse_package_spec("acme-ext")

    assert (local.kind, local.location) == ("local", "./tools/kit")
    assert (git_pinned.kind, git_pinned.location, git_pinned.rev) == (
        "git",
        "https://example.com/acme/ext.git",
        "1a2b3c",
    )
    assert (pypi_pinned.kind, pypi_pinned.location, pypi_pinned.rev) == (
        "pypi",
        "acme-ext",
        "2.0.0",
    )
    assert (pypi_loose.kind, pypi_loose.location) == ("pypi", "acme-ext")


def test_parse_rejects_ambiguous_or_empty_specs() -> None:
    with pytest.raises(PackageSpecError):
        parse_package_spec("")
    with pytest.raises(PackageSpecError):
        parse_package_spec("git+https://example.com/x.git@")
    with pytest.raises(PackageSpecError):
        parse_package_spec("acme==")
    with pytest.raises(PackageSpecError):
        parse_package_spec("bad name with spaces")


def _runner(responses: dict[tuple[str, ...], str]):
    def run(command: Sequence[str]) -> str:
        key = tuple(command)
        if key not in responses:
            raise AssertionError(f"unexpected command: {key}")
        return responses[key]

    return run


def test_local_resolution_hashes_directory_content_deterministically(tmp_path: Path) -> None:
    package = tmp_path / "kit"
    package.mkdir()
    (package / "main.py").write_text("print('hi')\n", encoding="utf-8")

    first = resolve_source(parse_package_spec(str(package)))
    second = resolve_source(parse_package_spec(str(package)))

    assert first.kind == "local"
    assert first.location == str(package.resolve())
    assert first.commit is None
    assert first.content_hash is not None
    assert first.content_hash == second.content_hash

    (package / "extra.py").write_text("x = 1\n", encoding="utf-8")
    changed = resolve_source(parse_package_spec(str(package)))

    assert changed.content_hash is not None
    assert changed.content_hash != first.content_hash


def test_git_resolution_reports_commit_and_detects_ref_drift() -> None:
    spec = parse_package_spec("git+https://example.com/acme/ext.git@1a2b3c")
    runner = _runner(
        {
            (
                "git",
                "ls-remote",
                "https://example.com/acme/ext.git",
                "1a2b3c",
            ): "cafe567\trefs/heads/main\n"
        }
    )

    resolved = resolve_source(spec, runner=runner)
    assert resolved.commit == "cafe567"
    assert resolved.content_hash is not None

    pinned = parse_package_spec("git+https://example.com/acme/ext.git@" + "0" * 40)
    drift_runner = _runner(
        {("git", "ls-remote", "https://example.com/acme/ext.git", "0" * 40): "f" * 40 + "\n"}
    )

    with pytest.raises(RefDriftError):
        resolve_source(pinned, runner=drift_runner)


def test_offline_runner_failure_maps_to_typed_error(tmp_path: Path) -> None:
    def offline(_command: Sequence[str]) -> str:
        raise OSError("network disabled")

    with pytest.raises(OfflineResolutionError):
        resolve_source(
            parse_package_spec("git+https://example.com/a/b.git"),
            runner=offline,
        )
