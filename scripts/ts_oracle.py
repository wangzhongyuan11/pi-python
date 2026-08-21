"""Guarded, read-only entry point to the frozen TypeScript source tree."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

FROZEN_COMMIT = "e14afc648e10fb6c527ea88fa627091ada764306"


class OracleError(RuntimeError):
    """Raised when the TypeScript source or requested operation is unsafe."""


def resolve_source(
    source: str | Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> Path:
    environment = os.environ if environ is None else environ
    raw_source = source if source is not None else environment.get("PI_TS_SOURCE")
    if raw_source is None or not str(raw_source).strip():
        raise OracleError("set PI_TS_SOURCE to the read-only TypeScript source tree")

    resolved = Path(raw_source).expanduser().resolve()
    if not resolved.is_dir():
        raise OracleError(f"TypeScript source directory does not exist: {resolved}")
    return resolved


def _run_git(source: Path, *arguments: str) -> str:
    environment = os.environ.copy()
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        completed = subprocess.run(
            ["git", "-C", str(source), *arguments],
            check=False,
            capture_output=True,
            env=environment,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise OracleError(f"could not run git: {exc}") from exc

    if completed.returncode != 0:
        detail = completed.stderr.strip() or "git command failed"
        raise OracleError(detail)
    return completed.stdout.strip()


def current_commit(source: Path) -> str:
    commit = _run_git(source, "rev-parse", "HEAD")
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise OracleError(f"unexpected git commit output: {commit!r}")
    return commit


def verify_clean_worktree(source: Path) -> None:
    status = _run_git(source, "status", "--porcelain=v1", "--untracked-files=all")
    if status:
        raise OracleError("TypeScript source worktree is not clean")


def verify_frozen_commit(source: Path, *, expected: str = FROZEN_COMMIT) -> str:
    actual = current_commit(source)
    if actual != expected:
        raise OracleError(
            f"TypeScript source commit {actual} does not match frozen commit {expected}"
        )
    verify_clean_worktree(source)
    return actual


def reject_npm_script_execution(name: str) -> None:
    """Keep the Phase 0 oracle read-only; execution requires a copied checkout."""

    raise OracleError(
        f"npm script {name!r} is not read-only: Phase 0 never executes npm in PI_TS_SOURCE"
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        help="TypeScript source tree (defaults to PI_TS_SOURCE)",
    )
    parser.add_argument(
        "--expect-commit",
        help="verify this commit and print it",
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("commit", help="print the current TypeScript source commit")
    subparsers.add_parser("verify", help="verify and print the frozen TypeScript commit")
    npm_parser = subparsers.add_parser("npm", help="reject npm execution in the source tree")
    npm_parser.add_argument("script")
    npm_parser.add_argument("arguments", nargs=argparse.REMAINDER)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _build_parser().parse_args(argv)
    source = resolve_source(arguments.source)

    if arguments.command == "npm":
        reject_npm_script_execution(arguments.script)
    if arguments.expect_commit is not None:
        if arguments.command is not None:
            raise OracleError("--expect-commit cannot be combined with a subcommand")
        print(verify_frozen_commit(source, expected=arguments.expect_commit))
        return 0
    if arguments.command in {None, "commit"}:
        print(current_commit(source))
        return 0
    if arguments.command == "verify":
        print(verify_frozen_commit(source))
        return 0

    raise OracleError(f"unsupported command: {arguments.command}")


def _entrypoint() -> None:
    try:
        raise SystemExit(main())
    except OracleError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    _entrypoint()
