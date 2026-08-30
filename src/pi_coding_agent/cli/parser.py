"""Static Phase 6 command-line parser."""

from __future__ import annotations

import argparse


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


def create_parser(*, version: str) -> argparse.ArgumentParser:
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
    return parser


def create_run_parser(*, version: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pi-python")
    _add_common(parser, version=version)
    parser.add_argument("--mode", choices=("text", "json"), default="text")
    parser.add_argument("--print", "-p", action="store_true", dest="print_mode")
    parser.add_argument("--tui-mode", choices=("regular", "fullscreen"), default="regular")
    parser.add_argument("--provider", default="deepseek")
    parser.add_argument("--model")
    parser.add_argument(
        "--thinking",
        choices=("off", "minimal", "low", "medium", "high", "xhigh", "max"),
        default="high",
    )
    sessions = parser.add_mutually_exclusive_group()
    sessions.add_argument("--no-session", action="store_true")
    sessions.add_argument("--session")
    sessions.add_argument("--resume", "-r", action="store_true")
    sessions.add_argument("--continue", "-c", action="store_true", dest="continue_session")
    parser.add_argument("--session-dir")
    parser.add_argument("messages", nargs="*")
    return parser


__all__ = ["create_parser", "create_run_parser"]
