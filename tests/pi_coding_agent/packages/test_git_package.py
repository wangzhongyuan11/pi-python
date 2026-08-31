from __future__ import annotations

import json
import shutil
from collections.abc import Sequence
from pathlib import Path

from pi_coding_agent.config.settings import SettingsManager
from pi_coding_agent.packages.manager import DefaultPackageManager


class FakeGitRemote:
    def __init__(self, root: Path) -> None:
        self._root = root
        self.refs = {"main": "a" * 40}

    def add_version(self, commit: str, body: str) -> None:
        package = self._root / commit
        (package / "skills").mkdir(parents=True)
        (package / "package.json").write_text(
            json.dumps({"name": "git-package", "pi": {"skills": ["skills"]}}),
            encoding="utf-8",
        )
        (package / "skills" / "git.md").write_text(body, encoding="utf-8")

    def __call__(self, command: Sequence[str]) -> str:
        if command[:2] == ("git", "ls-remote"):
            ref = command[-1]
            commit = self.refs.get(ref, ref if len(ref) == 40 else "")
            return f"{commit}\trefs/heads/{ref}\n" if commit else ""
        if command[:3] == ("git", "clone", "--quiet"):
            Path(command[-1]).mkdir(parents=True)
            return ""
        if len(command) >= 6 and command[:2] == ("git", "-C") and command[3] == "checkout":
            target = Path(command[2])
            commit = command[-1]
            shutil.copytree(self._root / commit, target, dirs_exist_ok=True)
            return ""
        raise AssertionError(f"unexpected git command: {command}")


def _manager(tmp_path: Path, remote: FakeGitRemote) -> DefaultPackageManager:
    return DefaultPackageManager(
        settings=SettingsManager.load(
            agent_dir=tmp_path / "agent",
            cwd=tmp_path / "project",
            project_trusted=True,
        ),
        command_runner=remote,
    )


def test_git_branch_update_replaces_resources_but_pinned_commit_stays_fixed(
    tmp_path: Path,
) -> None:
    remote = FakeGitRemote(tmp_path / "remote")
    first = "a" * 40
    second = "b" * 40
    remote.add_version(first, "version one")
    remote.add_version(second, "version two")
    branch_source = "git+https://example.invalid/golden.git@main"
    manager = _manager(tmp_path, remote)

    manager.install_git(branch_source)
    installed = tmp_path / "agent" / "packages" / "git-package" / "skills" / "git.md"
    assert installed.read_text(encoding="utf-8") == "version one"
    assert manager.list_configured_packages()[0].source == branch_source

    remote.refs["main"] = second
    manager.update_git(branch_source)
    assert installed.read_text(encoding="utf-8") == "version two"

    pinned_source = f"git+https://example.invalid/golden.git@{first}"
    manager.remove_installed(branch_source)
    manager.install_git(pinned_source)
    remote.refs["main"] = second
    manager.update_git(pinned_source)
    assert installed.read_text(encoding="utf-8") == "version one"
