from __future__ import annotations

import os
from pathlib import Path

import pytest

from pi_coding_agent.session import atomic


def test_atomic_write_replaces_target_and_uses_same_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "session.jsonl"
    target.write_bytes(b"old")
    observed: list[tuple[Path, Path]] = []
    real_replace = os.replace

    def record_replace(
        source: str | os.PathLike[str],
        dest: str | os.PathLike[str],
    ) -> None:
        observed.append((Path(source), Path(dest)))
        real_replace(source, dest)

    monkeypatch.setattr(atomic.os, "replace", record_replace)

    atomic.atomic_write(target, b"new\n")

    assert target.read_bytes() == b"new\n"
    assert observed[0][0].parent == target.parent
    assert observed[0][1] == target
    assert list(tmp_path.glob("*.tmp")) == []


def test_replace_failure_preserves_target_and_removes_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "session.jsonl"
    target.write_bytes(b"original")

    def fail_replace(*_args: object) -> None:
        raise OSError("injected replace failure")

    monkeypatch.setattr(atomic.os, "replace", fail_replace)

    with pytest.raises(OSError, match="injected"):
        atomic.atomic_write(target, b"replacement")

    assert target.read_bytes() == b"original"
    assert [item for item in tmp_path.iterdir() if item.suffix == ".tmp"] == []


def test_atomic_create_never_overwrites_an_existing_target(tmp_path: Path) -> None:
    target = tmp_path / "session.jsonl"
    target.write_bytes(b"existing")

    with pytest.raises(FileExistsError):
        atomic.atomic_create(target, b"new")

    assert target.read_bytes() == b"existing"
