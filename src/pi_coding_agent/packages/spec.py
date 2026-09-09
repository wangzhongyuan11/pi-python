"""Extension package spec parsing for local, Git, and PyPI sources."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

SpecKind = Literal["local", "git", "npm", "pypi"]

_PYPI_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_NPM_NAME_RE = re.compile(r"^(?:@[A-Za-z0-9._-]+/)?[A-Za-z0-9._-]+$")
_FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_GIT_PROTOCOLS = ("https://", "http://", "ssh://", "git://")


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
    text = text.strip()
    if not text:
        raise PackageSpecError("package spec is empty")
    if text.startswith("npm:"):
        return _parse_npm(text)
    if text.startswith("git+"):
        return _parse_git(text[len("git+") :], original=text, require_protocol=True)
    if text.startswith("git:"):
        remainder = text[len("git:") :]
        if not remainder:
            raise PackageSpecError("git package location is empty")
        return _parse_git(remainder, original=text, require_protocol=False)
    if text.startswith(_GIT_PROTOCOLS):
        return _parse_git(text, original=text, require_protocol=True)
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


def _parse_npm(text: str) -> PackageSpec:
    spec = text[len("npm:") :].strip()
    if not spec:
        raise PackageSpecError("npm package name is empty")
    if spec.startswith("@"):
        slash = spec.find("/")
        if slash == -1:
            raise PackageSpecError(f"invalid npm spec: {text!r}")
        at_index = spec.find("@", slash)
    else:
        at_index = spec.find("@")
    name = spec if at_index == -1 else spec[:at_index]
    rev = None if at_index == -1 else spec[at_index + 1 :]
    if not _NPM_NAME_RE.fullmatch(name) or rev == "":
        raise PackageSpecError(f"invalid npm spec: {text!r}")
    return PackageSpec(kind="npm", location=name, rev=rev)


def _parse_git(remainder: str, *, original: str, require_protocol: bool) -> PackageSpec:
    if original.endswith("@"):
        raise PackageSpecError(f"git spec has an empty revision: {original!r}")
    at_index = remainder.rfind("@")
    separator = max(remainder.rfind("/"), remainder.rfind(":"))
    if at_index > separator:
        location = remainder[:at_index]
        rev = remainder[at_index + 1 :]
    else:
        location = remainder
        rev = None
    if not location:
        raise PackageSpecError(f"git package location is empty: {original!r}")
    if location.startswith(_GIT_PROTOCOLS) or re.match(r"^[^/@]+@[^:]+:.+", location):
        return PackageSpec(kind="git", location=location, rev=rev)
    if require_protocol or "/" not in location:
        raise PackageSpecError(f"unsupported git location: {location!r}")
    return PackageSpec(kind="git", location=f"https://{location}", rev=rev)


def package_identity(spec: PackageSpec) -> str:
    if spec.kind == "npm":
        return f"npm:{spec.location}"
    if spec.kind != "git":
        return f"{spec.kind}:{spec.location}"
    location = spec.location
    if re.match(r"^[^/@]+@[^:]+:.+", location):
        _user, host_path = location.split("@", 1)
        host, path = host_path.split(":", 1)
    else:
        parsed = urlparse(location)
        host = parsed.hostname or ""
        path = parsed.path.lstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    return f"git:{host.casefold()}/{path.rstrip('/')}"


def is_pinned_commit(rev: str) -> bool:
    return _FULL_SHA_RE.match(rev) is not None


__all__ = [
    "PackageSpec",
    "PackageSpecError",
    "SpecKind",
    "is_pinned_commit",
    "package_identity",
    "parse_package_spec",
]
