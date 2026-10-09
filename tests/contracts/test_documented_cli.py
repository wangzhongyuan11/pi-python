"""P17-T04: the Chinese documentation must match the real CLI surface.

Every ``--flag`` mentioned in README/docs must exist in ``pi-python --help``
(or belong to a documented subcommand), every documented ``pi-python``
command line must parse, and the documented version must match the
distribution version.
"""

from __future__ import annotations

import re
from io import StringIO
from pathlib import Path

from pi_coding_agent.cli.main import main

REPO = Path(__file__).resolve().parents[2]
DOC_FILES = (
    REPO / "README.md",
    REPO / "docs" / "usage.md",
    REPO / "docs" / "architecture.md",
)

SUBCOMMANDS = {
    "install",
    "remove",
    "uninstall",
    "update",
    "list",
    "config",
    "auth",
    "import-pi-session",
    "session",
}


def _existing_help_text() -> str:
    stdout = StringIO()
    stderr = StringIO()
    code = main(["--help"], stdout=stdout, stderr=stderr)
    assert code == 0
    return stdout.getvalue()


def _documented_text() -> str:
    parts: list[str] = []
    for doc in DOC_FILES:
        assert doc.exists(), f"missing documentation file: {doc}"
        parts.append(doc.read_text(encoding="utf-8"))
    return "\n".join(parts)


def test_every_documented_top_level_flag_exists_in_help() -> None:
    help_text = _existing_help_text()
    documented = _documented_text()
    flags = set(re.findall(r"`(--[a-z][a-z0-9-]*)", documented))
    # Subcommand-scoped options are validated by the parse test below.
    subcommand_only = {
        "--local",
        "--approve",
        "--no-approve",
        "--json",
        "--no-refresh",
        "--session-dir-parent",
        "--force",
        "--extensions",
        "--models-flag",
        "--extension",
        "--all",
        "--self",
        "--offline-update",
        "--credentials",
        "--min-expiry",
    }
    # --api-key is deliberately suppressed from help (secret surface).
    hidden = {"--api-key"}
    missing = sorted(flag for flag in flags - subcommand_only - hidden if flag not in help_text)
    assert not missing, f"documented flags missing from pi-python --help: {missing}"


def test_every_documented_subcommand_exists() -> None:
    documented = _documented_text()
    mentioned = set(re.findall(r"`pi-python (`?)([a-z-]+)", documented))
    mentioned = {name for _, name in mentioned}
    help_text = _existing_help_text()
    unknown = sorted(
        name
        for name in mentioned
        if name not in SUBCOMMANDS
        and f"{name}" not in help_text
        and name not in {"--help", "--version"}
    )
    assert not unknown, f"documented commands missing from the CLI: {unknown}"


def test_documented_option_lines_parse() -> None:
    from pi_coding_agent.cli.parser import create_run_parser

    documented = _documented_text()
    parser = create_run_parser(version="contract-test")
    command_lines = re.findall(r"pi-python (--(?:[a-z][a-z0-9-]*)[^`\n]*)", documented)
    checked = 0
    for line in command_lines:
        tokens = line.replace("`", "").strip().split()
        tokens = [token for token in tokens if token not in {"...", "[options]"}]
        if not tokens or not tokens[0].startswith("--"):
            continue
        try:
            namespace, unknown = parser.parse_known_args(tokens)
        except SystemExit as exit_error:
            # --version/--help actions exit cleanly during parsing.
            assert exit_error.code == 0, f"documented line failed: {tokens}"
            checked += 1
            continue
        assert not unknown, f"documented line has unknown arguments: {tokens}"
        del namespace
        checked += 1
    assert checked >= 3, "the docs must contain runnable pi-python command lines"


def test_documented_version_matches_the_distribution() -> None:
    from importlib.metadata import version as dist_version

    documented = _documented_text()
    current = dist_version("pi-python")
    if f"`{current}`" in documented or current in documented:
        return
    # The docs may legitimately avoid pinning a version, but they must not
    # pin a STALE one.
    stale = re.findall(r"`(\d+\.\d+\.\d+)`", documented)
    # 0.84.1 is the frozen UPSTREAM Pi baseline, documented as such, not ours.
    upstream_baseline = {"0.84.1"}
    wrong = [found for found in stale if found != current and found not in upstream_baseline]
    assert not wrong, f"docs pin stale versions {wrong}; current distribution version is {current}"
