"""Static Phase 6 command-line parser."""

from __future__ import annotations

import argparse


def create_parser(*, version: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pi-python")
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


__all__ = ["create_parser"]
