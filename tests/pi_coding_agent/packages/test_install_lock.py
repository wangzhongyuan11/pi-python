from __future__ import annotations

from pathlib import Path

import pytest

from pi_coding_agent.packages.environment import EnvironmentInstallError, ManagedEnvironment
from pi_coding_agent.packages.lockfile import LockfileWriteError, load_entries, save_entries


def _fake_installer(record: dict[str, str]):
    def install(source_location: str, target_dir: Path) -> None:
        target_dir.mkdir(parents=True)
        (target_dir / "installed.marker").write_text(source_location, encoding="utf-8")
        record[source_location] = str(target_dir)

    return install


def test_install_creates_target_and_writes_atomic_lockfile(tmp_path: Path) -> None:
    package = tmp_path / "src" / "kit"
    package.mkdir(parents=True)
    (package / "main.py").write_text("print('x')\n", encoding="utf-8")

    environment = ManagedEnvironment(
        root=tmp_path / "managed",
        installer=_fake_installer({}),
    )
    entry = environment.install(str(package))

    lock_path = tmp_path / "managed" / "extensions-lock.json"
    assert entry.name == "kit"
    assert entry.content_hash
    assert lock_path.exists()
    assert not list(lock_path.parent.glob("*.tmp"))
    assert (tmp_path / "managed" / "env" / "kit" / "installed.marker").exists()


def test_install_failure_rolls_back_lockfile_and_target(tmp_path: Path) -> None:
    good = tmp_path / "good"
    good.mkdir()

    environment = ManagedEnvironment(root=tmp_path / "managed", installer=_fake_installer({}))
    environment.install(str(good))
    lock_path = tmp_path / "managed" / "extensions-lock.json"
    before = lock_path.read_bytes()

    def broken_installer(_location: str, target_dir: Path) -> None:
        target_dir.mkdir(parents=True)
        raise RuntimeError("uv exploded mid-install")

    failing = ManagedEnvironment(root=tmp_path / "managed", installer=broken_installer)

    with pytest.raises(EnvironmentInstallError):
        failing.install(str(tmp_path / "other"))

    assert lock_path.read_bytes() == before
    assert not (tmp_path / "managed" / "env" / "other").exists()


def test_update_replaces_entry_for_same_name(tmp_path: Path) -> None:
    v1 = tmp_path / "pkg"
    v1.mkdir()
    environment = ManagedEnvironment(root=tmp_path / "managed", installer=_fake_installer({}))
    original = environment.install(str(v1))

    (v1 / "main.py").write_text("new content\n", encoding="utf-8")
    updated = environment.update(original.name, str(v1))

    assert updated.name == original.name
    assert updated.content_hash != original.content_hash
    assert [item.name for item in environment.entries()] == [original.name]


def test_lockfile_survives_reload_round_trip(tmp_path: Path) -> None:
    package = tmp_path / "kit"
    package.mkdir()
    environment = ManagedEnvironment(root=tmp_path / "managed", installer=_fake_installer({}))
    entry = environment.install(str(package))

    reloaded = load_entries(tmp_path / "managed" / "extensions-lock.json")

    assert list(reloaded) == [entry]
    with pytest.raises(LockfileWriteError):
        save_entries(Path("Z:/definitely/not/a/dir/lock.json"), ())
