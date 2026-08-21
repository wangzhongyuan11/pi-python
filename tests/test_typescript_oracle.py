from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.ts_oracle import (
    FROZEN_COMMIT,
    OracleError,
    current_commit,
    main,
    reject_npm_script_execution,
    resolve_source,
    verify_frozen_commit,
)


def _create_git_repository(path: Path) -> Path:
    path.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=path, check=True)
    (path / "README.md").write_text("oracle fixture\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Pi Tests",
            "-c",
            "user.email=pi-tests@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "fixture",
        ],
        cwd=path,
        check=True,
    )
    return path


def test_source_defaults_to_pi_ts_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "typescript-source"
    source.mkdir()
    monkeypatch.setenv("PI_TS_SOURCE", str(source))

    assert resolve_source() == source.resolve()


def test_frozen_commit_is_the_phase_zero_baseline() -> None:
    assert FROZEN_COMMIT == "e14afc648e10fb6c527ea88fa627091ada764306"


def test_source_is_required_when_environment_variable_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PI_TS_SOURCE", raising=False)

    with pytest.raises(OracleError, match="PI_TS_SOURCE"):
        resolve_source()


def test_commit_can_be_printed_and_verified(tmp_path: Path) -> None:
    source = _create_git_repository(tmp_path / "typescript-source")
    actual = current_commit(source)

    assert len(actual) == 40
    assert verify_frozen_commit(source, expected=actual) == actual


def test_commit_command_prints_source_head(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = _create_git_repository(tmp_path / "typescript-source")

    assert main(["--source", str(source), "commit"]) == 0
    assert capsys.readouterr().out.strip() == current_commit(source)


def test_commit_command_remains_read_only_when_source_is_dirty(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = _create_git_repository(tmp_path / "typescript-source")
    (source / "README.md").write_text("changed but readable\n", encoding="utf-8")
    status_before = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=source,
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    assert main(["--source", str(source), "commit"]) == 0
    assert capsys.readouterr().out.strip() == current_commit(source)
    status_after = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=source,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert status_after == status_before


def test_expect_commit_option_verifies_and_prints_source_head(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = _create_git_repository(tmp_path / "typescript-source")
    actual = current_commit(source)

    assert main(["--source", str(source), "--expect-commit", actual]) == 0
    assert capsys.readouterr().out.strip() == actual


@pytest.mark.parametrize("dirty_kind", ["tracked", "staged", "untracked"])
def test_verification_rejects_every_kind_of_dirty_worktree(
    tmp_path: Path,
    dirty_kind: str,
) -> None:
    source = _create_git_repository(tmp_path / "typescript-source")
    actual = current_commit(source)
    if dirty_kind == "tracked":
        (source / "README.md").write_text("modified\n", encoding="utf-8")
    elif dirty_kind == "staged":
        (source / "README.md").write_text("staged\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=source, check=True)
    else:
        (source / "untracked.txt").write_text("untracked\n", encoding="utf-8")

    with pytest.raises(OracleError, match="worktree is not clean"):
        verify_frozen_commit(source, expected=actual)


def test_expect_commit_rejects_a_dirty_worktree(tmp_path: Path) -> None:
    source = _create_git_repository(tmp_path / "typescript-source")
    actual = current_commit(source)
    (source / "untracked.txt").write_text("untracked\n", encoding="utf-8")

    with pytest.raises(OracleError, match="worktree is not clean"):
        main(["--source", str(source), "--expect-commit", actual])


def test_frozen_commit_mismatch_is_rejected(tmp_path: Path) -> None:
    source = _create_git_repository(tmp_path / "typescript-source")

    with pytest.raises(OracleError, match="does not match frozen commit"):
        verify_frozen_commit(source, expected=FROZEN_COMMIT)


@pytest.mark.parametrize("name", ["check", "test:scripts", "typecheck"])
def test_all_npm_script_execution_is_rejected(name: str) -> None:
    with pytest.raises(OracleError, match="never executes npm"):
        reject_npm_script_execution(name)


def test_npm_command_is_rejected_before_any_process_starts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "typescript-source"
    source.mkdir()

    def fail_if_called(*args: object, **kwargs: object) -> None:
        del args, kwargs
        pytest.fail("npm rejection must not start a subprocess")

    monkeypatch.setattr(subprocess, "run", fail_if_called)

    with pytest.raises(OracleError, match="never executes npm"):
        main(["--source", str(source), "npm", "check"])
