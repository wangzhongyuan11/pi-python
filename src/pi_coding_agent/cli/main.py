"""Process boundary for the initial headless CLI surface."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Mapping, Sequence
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import TextIO

from pi_ai.credentials import CredentialResolutionError
from pi_ai.providers.deepseek import DEEPSEEK_MODELS, DEFAULT_DEEPSEEK_MODEL
from pi_coding_agent import __version__

from ..deepseek_credentials import DeepSeekCredentialResolver
from .parser import create_parser


def _resolver(
    arguments: argparse.Namespace,
    *,
    cwd: Path,
    environ: Mapping[str, str],
) -> DeepSeekCredentialResolver:
    env_file = None
    if arguments.env_file:
        candidate = Path(arguments.env_file)
        env_file = (candidate if candidate.is_absolute() else cwd / candidate).resolve()
    return DeepSeekCredentialResolver(
        api_key=arguments.api_key,
        environ=environ,
        env_file=env_file,
        cwd=cwd,
    )


def _resolve_key(resolver: DeepSeekCredentialResolver) -> str:
    value = asyncio.run(resolver.resolve("deepseek"))
    if value is None:
        raise RuntimeError("DeepSeek resolver returned no credential")
    return value


def _list_models(search: str, stdout: TextIO) -> int:
    query = search.casefold()
    for model in DEEPSEEK_MODELS:
        identity = f"{model.provider}/{model.id}"
        if query and query not in identity.casefold() and query not in model.name.casefold():
            continue
        suffix = " (default)" if model.id == DEFAULT_DEEPSEEK_MODEL.id else ""
        stdout.write(f"{identity}\t{model.name}{suffix}\n")
    return 0


def _auth(
    arguments: argparse.Namespace,
    *,
    stdout: TextIO,
    stderr: TextIO,
    cwd: Path,
    environ: Mapping[str, str],
) -> int:
    resolver = _resolver(arguments, cwd=cwd, environ=environ)
    try:
        key = _resolve_key(resolver)
    except CredentialResolutionError as error:
        if arguments.auth_command == "check" and arguments.json_output:
            stdout.write('{"provider":"deepseek","ready":false}\n')
        else:
            stderr.write(f"{error}\n")
        return 1
    if arguments.auth_command == "print-api-key":
        stdout.write(f"{key}\n")
    elif arguments.json_output:
        stdout.write(json.dumps({"provider": "deepseek", "ready": True}, separators=(",", ":")))
        stdout.write("\n")
    else:
        stdout.write("deepseek: ready\n")
    return 0


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    cwd: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> int:
    output = sys.stdout if stdout is None else stdout
    errors = sys.stderr if stderr is None else stderr
    runtime_cwd = Path.cwd() if cwd is None else cwd.resolve()
    runtime_environ = os.environ if environ is None else environ
    parser = create_parser(version=__version__)
    try:
        with redirect_stdout(output), redirect_stderr(errors):
            arguments = parser.parse_args(argv)
    except SystemExit as error:
        return error.code if isinstance(error.code, int) else int(error.code is not None)

    if arguments.list_models is not None:
        return _list_models(arguments.list_models, output)
    if arguments.command == "auth":
        return _auth(
            arguments,
            stdout=output,
            stderr=errors,
            cwd=runtime_cwd,
            environ=runtime_environ,
        )
    parser.print_help(output)
    return 0


__all__ = ["main"]
