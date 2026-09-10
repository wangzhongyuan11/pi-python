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
from typing import Literal, TextIO, cast

from pi_ai.credentials import CredentialResolutionError
from pi_ai.providers.deepseek import DEEPSEEK_MODELS, DEFAULT_DEEPSEEK_MODEL

from ..deepseek_credentials import DeepSeekCredentialResolver
from ..extensions.registry import ExtensionFlagError
from ..model_runtime import ModelRuntime, UnknownModelError
from ..providers import UnknownProviderError
from ..sdk import AgentSessionFactory, ToolSelection
from ..services import ServiceOverrides, create_product_services
from ..session.errors import SessionError
from ..tui.runner import InteractiveOptions, run_interactive
from .import_session import run_import_session
from .packages import run_package_command
from .parser import create_parser, create_run_parser, parse_run_arguments
from .run import HeadlessOptions, run_headless
from .session_repair import run_session_repair
from .surface import UnknownFlagError, format_extension_flag_help

_GLOBAL_VALUE_OPTIONS = {"--api-key", "--env-file"}
_PACKAGE_COMMANDS = frozenset({"install", "remove", "uninstall", "update", "list", "config"})
_COMMANDS = frozenset({"auth", "import-pi-session", "session"}) | _PACKAGE_COMMANDS


def tool_selection_from_arguments(arguments: argparse.Namespace) -> ToolSelection:
    from ..tools.registry import expand_tool_selection

    no_tools: Literal["all", "builtin"] | None = None
    if getattr(arguments, "no_tools", False):
        no_tools = "all"
    elif getattr(arguments, "no_builtin_tools", False):
        no_tools = "builtin"
    raw_tools = getattr(arguments, "tools", None)
    raw_exclude = getattr(arguments, "exclude_tools", None)
    return ToolSelection(
        no_tools=no_tools,
        tool_names=expand_tool_selection(raw_tools) if raw_tools else None,
        exclude_tools=expand_tool_selection(raw_exclude) if raw_exclude else None,
    )


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
        return value in _COMMANDS
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


async def _print_run_help(
    parser: argparse.ArgumentParser,
    *,
    stdout: TextIO,
    cwd: Path,
    service_overrides: ServiceOverrides,
) -> int:
    services = create_product_services(cwd, service_overrides)
    try:
        await services.extensions.start()
        registry = getattr(services.extensions, "registry", None)
        registrations = () if registry is None else registry.registrations("flag")
        stdout.write(parser.format_help())
        stdout.write(format_extension_flag_help(registrations))
    finally:
        await services.extensions.close()
    return 0


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stdin: TextIO | None = None,
    stderr: TextIO | None = None,
    cwd: Path | None = None,
    environ: Mapping[str, str] | None = None,
    model_runtime: ModelRuntime | None = None,
    service_overrides: ServiceOverrides | None = None,
    runtime_factory: AgentSessionFactory | None = None,
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
    if not command_mode and any(value in {"--help", "-h"} for value in raw_arguments):
        try:
            return asyncio.run(
                _print_run_help(
                    parser,
                    stdout=output,
                    cwd=runtime_cwd,
                    service_overrides=(
                        ServiceOverrides() if service_overrides is None else service_overrides
                    ),
                )
            )
        except KeyboardInterrupt:
            return 130
    extras: dict[str, bool | str] = {}
    try:
        with redirect_stdout(output), redirect_stderr(errors):
            if command_mode:
                arguments = parser.parse_args(raw_arguments)
            else:
                arguments, extras = parse_run_arguments(parser, raw_arguments)
    except UnknownFlagError as error:
        errors.write(f"Error: {error}\n")
        return 2
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
    if command_mode and arguments.command == "session":
        return run_session_repair(
            arguments.path,
            stdout=output,
            stderr=errors,
        )
    if command_mode and arguments.command in _PACKAGE_COMMANDS:
        return run_package_command(
            arguments,
            stdout=output,
            stderr=errors,
            cwd=runtime_cwd,
            environ=runtime_environ,
        )
    messages = cast("list[str]", arguments.messages)
    if arguments.mode == "rpc" and (messages or arguments.print_mode):
        errors.write("Error: RPC mode accepts commands on stdin, not positional prompts or -p\n")
        return 1
    tool_selection = tool_selection_from_arguments(arguments)
    project_trusted = bool(
        getattr(arguments, "approve", False) and not getattr(arguments, "no_approve", False)
    )
    session_name: str | None = None
    raw_name = getattr(arguments, "name", None)
    if raw_name is not None:
        session_name = " ".join(raw_name.split())
        if not session_name:
            errors.write("Error: --name requires a non-empty value\n")
            return 1
    session_dir = None
    if arguments.session_dir:
        candidate = Path(arguments.session_dir)
        session_dir = (candidate if candidate.is_absolute() else runtime_cwd / candidate).resolve()
    if arguments.mode == "rpc":
        from ..rpc.runner import run_rpc

        try:
            return asyncio.run(
                run_rpc(
                    HeadlessOptions(
                        cwd=runtime_cwd,
                        prompt="",
                        mode="json",
                        credential_resolver=_resolver(
                            arguments, cwd=runtime_cwd, environ=runtime_environ
                        ),
                        provider_id=arguments.provider,
                        model_id=arguments.model,
                        thinking_level=arguments.thinking,
                        no_session=arguments.no_session,
                        session=arguments.session,
                        resume=arguments.resume or arguments.continue_session,
                        session_dir=session_dir,
                        model_runtime=model_runtime,
                        tool_selection=tool_selection,
                        name=session_name,
                        service_overrides=service_overrides or ServiceOverrides(),
                        runtime_factory=runtime_factory,
                        project_trusted=project_trusted,
                        extension_flags=extras,
                    ),
                    stdin=sys.stdin if stdin is None else stdin,
                    stdout=output,
                    stderr=errors,
                )
            )
        except KeyboardInterrupt:
            return 130
        except ExtensionFlagError as error:
            errors.write(f"Error: {error}\n")
            return 2
        except (
            CredentialResolutionError,
            SessionError,
            UnknownModelError,
            UnknownProviderError,
            ValueError,
            OSError,
        ) as error:
            errors.write(f"RPC error: {error}\n")
            return 1
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
                        tool_selection=tool_selection,
                        name=session_name,
                        service_overrides=(
                            ServiceOverrides() if service_overrides is None else service_overrides
                        ),
                        runtime_factory=runtime_factory,
                        project_trusted=project_trusted,
                        extension_flags=extras,
                    ),
                    stdout=output,
                    stderr=errors,
                )
            )
        except KeyboardInterrupt:
            return 130
        except ExtensionFlagError as error:
            errors.write(f"Error: {error}\n")
            return 2
        except (
            CredentialResolutionError,
            SessionError,
            UnknownModelError,
            UnknownProviderError,
            ValueError,
        ) as error:
            errors.write(f"{error}\n")
            return 1
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
                    tool_selection=tool_selection,
                    name=session_name,
                    service_overrides=(
                        ServiceOverrides() if service_overrides is None else service_overrides
                    ),
                    runtime_factory=runtime_factory,
                    project_trusted=project_trusted,
                    extension_flags=extras,
                ),
                stdout=output,
                stderr=errors,
            )
        )
    except KeyboardInterrupt:
        return 130
    except ExtensionFlagError as error:
        errors.write(f"Error: {error}\n")
        return 2
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
