from __future__ import annotations

import json
from pathlib import Path

import pytest

from pi_coding_agent.config.models import PackageSource
from pi_coding_agent.packages.manifest import PackageManifestError, read_package_manifest


def _write(path: Path, text: str = "fixture") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _manifest(root: Path, pi: dict[str, object] | None) -> None:
    payload: dict[str, object] = {"name": "upstream-kit"}
    if pi is not None:
        payload["pi"] = pi
    _write(root / "package.json", json.dumps(payload))


def test_manifest_expands_upstream_globs_exclusions_and_conventional_directories(
    tmp_path: Path,
) -> None:
    root = tmp_path / "package"
    _manifest(
        root,
        {
            "extensions": ["extensions/*.ts", "!extensions/legacy.ts"],
            "skills": ["skills"],
            "prompts": ["prompts/*.md"],
            "themes": ["themes"],
        },
    )
    _write(root / "extensions/good.ts")
    _write(root / "extensions/legacy.ts")
    _write(root / "skills/nested/SKILL.md")
    _write(root / "prompts/review.md")
    _write(root / "themes/dark.json")

    manifest = read_package_manifest(root)

    assert {(item.kind, item.path.relative_to(root).as_posix()) for item in manifest.resources} == {
        ("extension", "extensions/good.ts"),
        ("skill", "skills"),
        ("prompt", "prompts/review.md"),
        ("theme", "themes"),
    }

    conventional = tmp_path / "conventional"
    _manifest(conventional, None)
    for directory in ("extensions", "skills", "prompts", "themes"):
        (conventional / directory).mkdir(parents=True)
    discovered = read_package_manifest(conventional)
    assert {item.path.name for item in discovered.resources} == {
        "extensions",
        "skills",
        "prompts",
        "themes",
    }


def test_object_filter_distinguishes_omitted_from_empty_and_supports_exact_delta(
    tmp_path: Path,
) -> None:
    root = tmp_path / "package"
    _manifest(root, {"skills": ["skills"], "prompts": ["prompts"]})
    _write(root / "skills/one/SKILL.md")
    _write(root / "prompts/one.md")
    _write(root / "prompts/extra.md")
    package_filter = PackageSource.model_validate(
        {
            "source": "./package",
            "skills": [],
            "prompts": ["prompts/*.md", "-prompts/one.md", "+other/manual.md"],
        }
    )
    _write(root / "other/manual.md")

    manifest = read_package_manifest(root, package_filter=package_filter)

    assert package_filter.extensions is None
    assert package_filter.skills == ()
    assert {(item.kind, item.path.relative_to(root).as_posix()) for item in manifest.resources} == {
        ("prompt", "other/manual.md"),
        ("prompt", "prompts/extra.md"),
    }


@pytest.mark.parametrize("entry", ["../outside", "/absolute", "C:/absolute"])
def test_manifest_rejects_paths_outside_package_root(tmp_path: Path, entry: str) -> None:
    root = tmp_path / "package"
    _manifest(root, {"skills": [entry]})

    with pytest.raises(PackageManifestError, match="outside package root"):
        read_package_manifest(root)
