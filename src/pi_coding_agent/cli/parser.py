"""Command-line parser: static surface plus two-phase extension flags."""

from __future__ import annotations

import argparse

from .surface import partition_extension_flags

_THINKING_LEVELS = ("off", "minimal", "low", "medium", "high", "xhigh", "max")


def _add_common(parser: argparse.ArgumentParser, *, version: str) -> None:
    parser.add_argument("--version", "-v", action="version", version=f"pi-python {version}")
    parser.add_argument(
        "--list-models",
        nargs="?",
        const="",
        metavar="SEARCH",
        help="list built-in models and exit",
    )
    parser.add_argument("--api-key", help=argparse.SUPPRESS)
    parser.add_argument("--env-file", type=str, help="read DEEPSEEK_API_KEY from this file")


def _add_package_commands(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],  # pyright: ignore[reportPrivateUsage]
) -> None:
    approve = argparse.ArgumentParser(add_help=False)
    approve.add_argument("--local", "-l", action="store_true", dest="local")
    approve.add_argument("--approve", "-a", action="store_true", dest="approve")
    approve.add_argument("--no-approve", "-na", action="store_true", dest="no_approve")

    install = commands.add_parser("install", parents=[approve], help="install a Python package")
    install.add_argument("source")
    remove = commands.add_parser("remove", parents=[approve], help="remove a package")
    remove.add_argument("source")
    uninstall = commands.add_parser("uninstall", parents=[approve], help="alias for remove")
    uninstall.add_argument("source")

    update = commands.add_parser("update", parents=[approve], help="update packages")
    update.add_argument("source", nargs="?", help="package source, or 'self'/'pi'")
    update.add_argument("--self", action="store_true", dest="self_update")
    update.add_argument("--extensions", action="store_true")
    update.add_argument("--models", action="store_true")
    update.add_argument("--all", action="store_true")
    update.add_argument("--extension", action="append")
    update.add_argument("--force", action="store_true")
    update.add_argument("--offline", action="store_true")

    commands.add_parser("list", help="list installed packages")
    config = commands.add_parser("config", parents=[approve], help="toggle package resources")
    config.add_argument("name", nargs="?")
    config.add_argument("state", nargs="?", choices=("enabled", "disabled"))


def create_parser(*, version: str) -> argparse.ArgumentParser:
    """Parser for the command mode: auth, session, and package subcommands."""
    parser = argparse.ArgumentParser(prog="pi-python")
    _add_common(parser, version=version)

    commands = parser.add_subparsers(dest="command")
    auth = commands.add_parser("auth", help="inspect DeepSeek credential readiness")
    auth_commands = auth.add_subparsers(dest="auth_command", required=True)
    check = auth_commands.add_parser("check", help="check whether a credential is available")
    check.add_argument("--json", action="store_true", dest="json_output")
    check.add_argument("--no-refresh", action="store_true", help=argparse.SUPPRESS)
    auth_commands.add_parser(
        "print-api-key",
        help="explicitly print the resolved DeepSeek API key",
    )
    importer = commands.add_parser(
        "import-pi-session",
        help="validate and import one upstream Session v3 file",
    )
    importer.add_argument("source")
    importer.add_argument("--session-dir")

    session = commands.add_parser("session", help="session maintenance commands")
    session_commands = session.add_subparsers(dest="session_command", required=True)
    repair = session_commands.add_parser(
        "repair",
        help="truncate a torn trailing record so a crashed session can open again",
    )
    repair.add_argument("path")

    _add_package_commands(commands)
    return parser


def create_run_parser(*, version: str) -> argparse.ArgumentParser:
    """Parser for the interactive/headless run mode."""
    parser = argparse.ArgumentParser(prog="pi-python")
    _add_common(parser, version=version)
    parser.add_argument("--mode", choices=("text", "json", "rpc"), default="text")
    parser.add_argument("--print", "-p", action="store_true", dest="print_mode")
    parser.add_argument("--tui-mode", choices=("regular", "fullscreen"), default="regular")
    parser.add_argument("--provider", default="deepseek")
    parser.add_argument("--model")
    parser.add_argument(
        "--thinking",
        choices=_THINKING_LEVELS,
        default=None,
    )
    parser.add_argument("--system-prompt")
    parser.add_argument("--append-system-prompt", action="append", dest="append_system_prompt")
    sessions = parser.add_mutually_exclusive_group()
    sessions.add_argument("--no-session", action="store_true")
    sessions.add_argument("--session")
    sessions.add_argument("--session-id")
    sessions.add_argument("--fork")
    sessions.add_argument("--resume", "-r", action="store_true")
    sessions.add_argument("--continue", "-c", action="store_true", dest="continue_session")
    parser.add_argument("--session-dir")
    parser.add_argument("--name", "-n", help="set a display name for the session")
    parser.add_argument(
        "--models",
        type=lambda value: [item.strip() for item in value.split(",") if item.strip()],
        help="comma-separated model rotation scope",
    )
    parser.add_argument("--no-tools", "-nt", action="store_true", help="disable all tools")
    parser.add_argument(
        "--no-builtin-tools", "-nbt", action="store_true", help="disable the built-in tools"
    )
    parser.add_argument(
        "--tools", "-t", help="comma-separated built-in tool allowlist ('all' selects every tool)"
    )
    parser.add_argument("--exclude-tools", "-xt", help="comma-separated built-in tool denylist")
    parser.add_argument("--extension", "-e", action="append", help=argparse.SUPPRESS)
    parser.add_argument("--no-extensions", "-ne", action="store_true", dest="no_extensions")
    parser.add_argument("--skill", action="append")
    parser.add_argument("--no-skills", "-ns", action="store_true", dest="no_skills")
    parser.add_argument("--prompt-template", action="append", dest="prompt_template")
    parser.add_argument(
        "--no-prompt-templates", "-np", action="store_true", dest="no_prompt_templates"
    )
    parser.add_argument("--theme", action="append")
    parser.add_argument("--use-theme", dest="use_theme")
    parser.add_argument("--no-themes", action="store_true", dest="no_themes")
    parser.add_argument("--no-context-files", "-nc", action="store_true", dest="no_context_files")
    parser.add_argument("--export")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--approve", "-a", action="store_true", dest="approve")
    parser.add_argument("--no-approve", "-na", action="store_true", dest="no_approve")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("messages", nargs="*")
    return parser


def parse_run_arguments(
    parser: argparse.ArgumentParser,
    arguments: list[str],
) -> tuple[argparse.Namespace, dict[str, bool | str]]:
    """Two-phase parse: static flags, then extension ``--flag[=value]`` tokens."""
    static_arguments, extension_flags = partition_extension_flags(
        arguments,
        known_options=parser._option_string_actions,  # pyright: ignore[reportPrivateUsage]
    )
    return parser.parse_args(static_arguments), extension_flags


__all__ = ["create_parser", "create_run_parser", "parse_run_arguments"]
