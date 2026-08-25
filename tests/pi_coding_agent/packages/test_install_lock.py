from __future__ import annotations

import json
from pathlib import Path

import pytest

import pi_coding_agent.packages.environment as environment_module
from pi_coding_agent.packages.environment import EnvironmentInstallError, ManagedEnvironment
from pi_coding_agent.packages.lockfile import (
    LockfileError,
    LockfileWriteError,
    load_entries,
    save_entries,
)
from pi_coding_agent.packages.resolver import ResolvedSource


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


def test_failed_update_preserves_previous_environment_and_lock(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    managed_root = tmp_path / "managed"
    environment = ManagedEnvironment(root=managed_root, installer=_fake_installer({}))
    original = environment.install(str(package))
    target = managed_root / "env" / original.name
    marker_before = (target / "installed.marker").read_bytes()
    lock_before = environment.lock_path.read_bytes()

    def broken_installer(_location: str, target_dir: Path) -> None:
        target_dir.mkdir(parents=True)
        (target_dir / "partial").write_text("incomplete", encoding="utf-8")
        raise RuntimeError("install failed")

    failing = ManagedEnvironment(root=managed_root, installer=broken_installer)
    with pytest.raises(EnvironmentInstallError):
        failing.update(original.name, str(package))

    assert (target / "installed.marker").read_bytes() == marker_before
    assert environment.lock_path.read_bytes() == lock_before
    assert not list((managed_root / "env").glob("*.staging"))


def test_update_rejects_names_that_escape_environment_root(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    victim = tmp_path / "victim"
    victim.mkdir()
    marker = victim / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    environment = ManagedEnvironment(root=tmp_path / "managed", installer=_fake_installer({}))

    with pytest.raises(EnvironmentInstallError):
        environment.update("../../victim", str(package))

    assert marker.read_text(encoding="utf-8") == "keep"


def test_installer_receives_resolved_pypi_pin(tmp_path: Path) -> None:
    installed: dict[str, str] = {}
    environment = ManagedEnvironment(
        root=tmp_path / "managed", installer=_fake_installer(installed)
    )

    environment.install("demo==1.2.3")

    assert set(installed) == {"demo==1.2.3"}


def test_installer_receives_resolved_git_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed: dict[str, str] = {}
    commit = "a" * 40
    monkeypatch.setattr(
        environment_module,
        "resolve_source",
        lambda _spec: ResolvedSource(
            kind="git",
            location="https://example.com/acme/ext.git",
            version=None,
            commit=commit,
            content_hash="hash",
        ),
    )
    environment = ManagedEnvironment(
        root=tmp_path / "managed", installer=_fake_installer(installed)
    )

    environment.install("git+https://example.com/acme/ext.git@main")

    assert set(installed) == {f"git+https://example.com/acme/ext.git@{commit}"}


def test_lock_failure_restores_previous_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    managed_root = tmp_path / "managed"
    environment = ManagedEnvironment(root=managed_root, installer=_fake_installer({}))
    original = environment.install(str(package))
    target = managed_root / "env" / original.name
    marker_before = (target / "installed.marker").read_bytes()
    lock_before = environment.lock_path.read_bytes()

    def fail_lock(_path: Path, _entries: object) -> None:
        raise LockfileWriteError("simulated lock failure")

    monkeypatch.setattr(environment_module, "save_entries", fail_lock)

    with pytest.raises(EnvironmentInstallError):
        environment.update(original.name, str(package))

    assert (target / "installed.marker").read_bytes() == marker_before
    assert environment.lock_path.read_bytes() == lock_before


def test_lockfile_survives_reload_round_trip(tmp_path: Path) -> None:
    package = tmp_path / "kit"
    package.mkdir()
    environment = ManagedEnvironment(root=tmp_path / "managed", installer=_fake_installer({}))
    entry = environment.install(str(package))

    reloaded = load_entries(tmp_path / "managed" / "extensions-lock.json")

    assert list(reloaded) == [entry]
    with pytest.raises(LockfileWriteError):
        save_entries(Path("Z:/definitely/not/a/dir/lock.json"), ())


@pytest.mark.parametrize(
    "payload",
    [
        [{}],
        [{"name": 3, "spec": "demo", "location": "demo"}],
        [{"name": "demo", "spec": "demo", "location": "demo", "version": 3}],
        [
            {"name": "demo", "spec": "demo", "location": "demo"},
            {"name": "demo", "spec": "demo2", "location": "demo2"},
        ],
    ],
)
def test_lockfile_rejects_missing_or_wrong_typed_fields(tmp_path: Path, payload: object) -> None:
    lock_path = tmp_path / "extensions-lock.json"
    lock_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(LockfileError):
        load_entries(lock_path)
