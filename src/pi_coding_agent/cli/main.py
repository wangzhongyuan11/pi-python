"""Process boundary for the initial headless CLI surface."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Mapping, Sequence
from contextlib import redirect_stderr, redirect_stdout
from importlib.metadata import version
from pathlib import Path
from typing import TextIO, cast

from pi_ai.credentials import CredentialResolutionError
from pi_ai.providers.deepseek import DEEPSEEK_MODELS, DEFAULT_DEEPSEEK_MODEL

from ..deepseek_credentials import DeepSeekCredentialResolver
from ..model_runtime import ModelRuntime, UnknownModelError
from ..providers import UnknownProviderError
from ..session.errors import SessionError
from ..tui.runner import InteractiveOptions, run_interactive
from .import_session import run_import_session
from .parser import create_parser, create_run_parser
from .run import HeadlessOptions, run_headless

_GLOBAL_VALUE_OPTIONS = {"--api-key", "--env-file"}


def _uses_command_parser(arguments: Sequence[str]) -> bool:
    index = 0
    while index < len(arguments):
        value = arguments[index]
        if any(value.startswith(f"{option}=") for option in _GLOBAL_VALUE_OPTIONS):
            index += 1
            continue
        if value in _GLOBAL_VALUE_OPTIONS:
            index += 2
            continue
        return value in {"auth", "import-pi-session"}
    return False


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
    model_runtime: ModelRuntime | None = None,
) -> int:
    output = sys.stdout if stdout is None else stdout
    errors = sys.stderr if stderr is None else stderr
    runtime_cwd = Path.cwd() if cwd is None else cwd.resolve()
    runtime_environ = os.environ if environ is None else environ
    raw_arguments = list(sys.argv[1:] if argv is None else argv)
    command_mode = _uses_command_parser(raw_arguments)
    parser = (
        create_parser(version=version("pi-python"))
        if command_mode
        else create_run_parser(version=version("pi-python"))
    )
    try:
        with redirect_stdout(output), redirect_stderr(errors):
            arguments = parser.parse_args(raw_arguments)
    except SystemExit as error:
        return error.code if isinstance(error.code, int) else int(error.code is not None)

    if arguments.list_models is not None:
        return _list_models(arguments.list_models, output)
    if command_mode and arguments.command == "auth":
        return _auth(
            arguments,
            stdout=output,
            stderr=errors,
            cwd=runtime_cwd,
            environ=runtime_environ,
        )
    if command_mode and arguments.command == "import-pi-session":
        return run_import_session(
            arguments.source,
            session_dir=arguments.session_dir,
            stdout=output,
            stderr=errors,
        )
    messages = cast("list[str]", arguments.messages)
    session_dir = None
    if arguments.session_dir:
        candidate = Path(arguments.session_dir)
        session_dir = (candidate if candidate.is_absolute() else runtime_cwd / candidate).resolve()
    if not messages:
        if arguments.print_mode or arguments.mode == "json":
            parser.print_help(output)
            return 0
        resolver = _resolver(arguments, cwd=runtime_cwd, environ=runtime_environ)
        try:
            return asyncio.run(
                run_interactive(
                    InteractiveOptions(
                        cwd=runtime_cwd,
                        credential_resolver=resolver,
                        provider_id=arguments.provider,
                        model_id=arguments.model,
                        thinking_level=arguments.thinking,
                        no_session=arguments.no_session,
                        session=arguments.session,
                        resume=arguments.resume or arguments.continue_session,
                        session_dir=session_dir,
                        model_runtime=model_runtime,
                        tui_mode=arguments.tui_mode,
                    ),
                    stdout=output,
                    stderr=errors,
                )
            )
        except KeyboardInterrupt:
            return 130
    resolver = _resolver(arguments, cwd=runtime_cwd, environ=runtime_environ)
    try:
        return asyncio.run(
            run_headless(
                HeadlessOptions(
                    cwd=runtime_cwd,
                    prompt=" ".join(messages),
                    mode=arguments.mode,
                    credential_resolver=resolver,
                    provider_id=arguments.provider,
                    model_id=arguments.model,
                    thinking_level=arguments.thinking,
                    no_session=arguments.no_session,
                    session=arguments.session,
                    resume=arguments.resume or arguments.continue_session,
                    session_dir=session_dir,
                    model_runtime=model_runtime,
                ),
                stdout=output,
                stderr=errors,
            )
        )
    except KeyboardInterrupt:
        return 130
    except (
        CredentialResolutionError,
        SessionError,
        UnknownModelError,
        UnknownProviderError,
        ValueError,
    ) as error:
        errors.write(f"{error}\n")
        return 1
    parser.print_help(output)
    return 0


__all__ = ["main"]
