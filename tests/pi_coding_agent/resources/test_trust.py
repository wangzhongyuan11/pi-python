from __future__ import annotations

from pathlib import Path

from pi_coding_agent.resources.trust import FileProjectTrustStore, TrustDecision


def test_trust_uses_canonical_path_and_nearest_ancestor(tmp_path: Path) -> None:
    real = tmp_path / "real"
    child = real / "child"
    child.mkdir(parents=True)
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    store = FileProjectTrustStore(tmp_path / "agent" / "trust.json")

    store.set(alias, TrustDecision.TRUSTED)

    entry = store.get_entry(child)
    assert entry is not None
    assert entry.path == real.resolve()
    assert entry.decision is TrustDecision.TRUSTED


def test_untrusted_child_overrides_trusted_parent(tmp_path: Path) -> None:
    parent = tmp_path / "workspace"
    child = parent / "unsafe"
    child.mkdir(parents=True)
    store = FileProjectTrustStore(tmp_path / "agent" / "trust.json")
    store.set(parent, TrustDecision.TRUSTED)
    store.set(child, TrustDecision.UNTRUSTED)

    assert store.get(child) is TrustDecision.UNTRUSTED
    assert store.get(parent / "safe") is TrustDecision.TRUSTED


def test_moved_project_does_not_inherit_old_exact_decision(tmp_path: Path) -> None:
    old = tmp_path / "old"
    old.mkdir()
    store = FileProjectTrustStore(tmp_path / "agent" / "trust.json")
    store.set(old, TrustDecision.TRUSTED)
    moved = tmp_path / "moved"
    old.rename(moved)

    assert store.get(moved) is TrustDecision.UNKNOWN


def test_unknown_is_default_and_removing_entry_restores_it(tmp_path: Path) -> None:
    project = tmp_path / "project"
    store = FileProjectTrustStore(tmp_path / "agent" / "trust.json")

    assert store.get(project) is TrustDecision.UNKNOWN
    store.set(project, TrustDecision.UNTRUSTED)
    store.set(project, TrustDecision.UNKNOWN)

    assert store.get(project) is TrustDecision.UNKNOWN
