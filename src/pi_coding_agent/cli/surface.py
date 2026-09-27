"""Two-phase CLI surface helpers: static flags plus extension flags."""

from __future__ import annotations

from collections.abc import Collection, Iterable

from ..extensions.registry import FlagState, Registration


class UnknownFlagError(ValueError):
    """An unknown short option, which only extensions may define dynamically."""


def split_unknown_flags(extras: list[str]) -> dict[str, bool | str]:
    """Map leftover ``--name[=value]`` tokens to extension flag values.

    Mirrors upstream two-phase parsing: ``--flag`` becomes ``True``,
    ``--flag=value`` and ``--flag value`` become strings. Unknown short
    options are a static-surface error.
    """
    mapping: dict[str, bool | str] = {}
    index = 0
    while index < len(extras):
        token = extras[index]
        if token == "--":
            index += 1
            continue
        if not token.startswith("--"):
            raise UnknownFlagError(f"unknown option: {token}")
        body = token[2:]
        if "=" in body:
            name, _, value = body.partition("=")
            mapping[name] = value
            index += 1
            continue
        following = extras[index + 1] if index + 1 < len(extras) else None
        if following is not None and not following.startswith(("-", "@")):
            mapping[body] = following
            index += 2
        else:
            mapping[body] = True
            index += 1
    return mapping


def partition_extension_flags(
    arguments: list[str],
    *,
    known_options: Collection[str],
) -> tuple[list[str], dict[str, bool | str]]:
    """Remove unknown long flags before argparse consumes positional messages."""
    static_arguments: list[str] = []
    extension_arguments: list[str] = []
    index = 0
    while index < len(arguments):
        token = arguments[index]
        if token == "--":
            static_arguments.extend(arguments[index:])
            break
        option = token.partition("=")[0]
        if option in known_options or not token.startswith("-"):
            static_arguments.append(token)
            index += 1
            continue
        if not token.startswith("--"):
            raise UnknownFlagError(f"unknown option: {token}")
        if "=" in token[2:]:
            extension_arguments.append(token)
            index += 1
            continue
        following = arguments[index + 1] if index + 1 < len(arguments) else None
        extension_arguments.append(token)
        if following is not None and not following.startswith(("-", "@")):
            extension_arguments.append(following)
            index += 2
        else:
            index += 1
    return static_arguments, split_unknown_flags(extension_arguments)


def format_extension_flag_help(registrations: Iterable[Registration]) -> str:
    """Render activated Extension flags after argparse's static help."""
    rows: list[str] = []
    for registration in registrations:
        if registration.kind != "flag":
            continue
        suffix = " <value>" if isinstance(registration.payload, FlagState) and (
            registration.payload.value_type == "string"
        ) else ""
        rows.append(f"  {registration.name}{suffix}\t({registration.source})")
    if not rows:
        return ""
    return "\nExtension flags:\n" + "\n".join(rows) + "\n"


__all__ = [
    "UnknownFlagError",
    "format_extension_flag_help",
    "partition_extension_flags",
    "split_unknown_flags",
]
