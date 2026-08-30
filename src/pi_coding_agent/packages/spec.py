"""Extension package spec parsing for local, Git, and PyPI sources."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

SpecKind = Literal["local", "git", "pypi"]

_PYPI_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class PackageSpecError(ValueError):
    """The spec text is empty, ambiguous, or violates its kind's syntax."""


@dataclass(frozen=True, slots=True)
class PackageSpec:
    kind: SpecKind
    location: str
    rev: str | None = None


def _looks_like_path(text: str) -> bool:
    return (
        text.startswith(("./", "../", "/", "~"))
        or (len(text) >= 3 and text[1:3] == ":\\")
        or (len(text) >= 2 and text[1] == ":/")
    )


def parse_package_spec(text: str) -> PackageSpec:
    if not text.strip():
        raise PackageSpecError("package spec is empty")
    if text.startswith("git+"):
        remainder = text[len("git+") :]
        at_index = _split_rev_index(remainder)
        if at_index == len(remainder):
            raise PackageSpecError(f"git spec has an empty revision: {text!r}")
        if at_index == -1:
            location = remainder
            rev = None
        else:
            location = remainder[:at_index]
            rev = remainder[at_index + 1 :]
            if not rev:
                raise PackageSpecError(f"git spec has an empty revision: {text!r}")
        if not location.startswith(("https://", "http://", "ssh://", "git://")):
            raise PackageSpecError(f"unsupported git location: {location!r}")
        return PackageSpec(kind="git", location=location, rev=rev)
    if _looks_like_path(text):
        return PackageSpec(kind="local", location=text)
    if "==" in text:
        name, _, version = text.partition("==")
        if not _PYPI_NAME_RE.match(name) or not version.strip():
            raise PackageSpecError(f"invalid PyPI spec: {text!r}")
        return PackageSpec(kind="pypi", location=name, rev=version)
    if _PYPI_NAME_RE.match(text):
        return PackageSpec(kind="pypi", location=text)
    raise PackageSpecError(f"unrecognized package spec: {text!r}")


def _split_rev_index(location: str) -> int:
    scheme_end = location.find("://")
    search_from = scheme_end + 3 if scheme_end != -1 else 0
    return location.find("@", search_from)


def is_pinned_commit(rev: str) -> bool:
    return _FULL_SHA_RE.match(rev) is not None


__all__ = ["PackageSpec", "PackageSpecError", "SpecKind", "is_pinned_commit", "parse_package_spec"]
