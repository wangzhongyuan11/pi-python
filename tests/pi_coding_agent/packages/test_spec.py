from __future__ import annotations

import pytest

from pi_coding_agent.packages.spec import (
    PackageSpecError,
    package_identity,
    parse_package_spec,
)


@pytest.mark.parametrize(
    ("text", "kind", "location", "rev"),
    [
        ("npm:@scope/pkg@1.2.3", "npm", "@scope/pkg", "1.2.3"),
        ("npm:plain-package", "npm", "plain-package", None),
        (
            "git:github.com/acme/pi-kit@v1",
            "git",
            "https://github.com/acme/pi-kit",
            "v1",
        ),
        (
            "git:git@github.com:acme/pi-kit@main",
            "git",
            "git@github.com:acme/pi-kit",
            "main",
        ),
        (
            "https://github.com/acme/pi-kit@release",
            "git",
            "https://github.com/acme/pi-kit",
            "release",
        ),
        (
            "ssh://git@github.com/acme/pi-kit@abc123",
            "git",
            "ssh://git@github.com/acme/pi-kit",
            "abc123",
        ),
        ("./local-kit", "local", "./local-kit", None),
        ("legacy-python==2.0", "pypi", "legacy-python", "2.0"),
    ],
)
def test_parse_upstream_and_legacy_package_sources(
    text: str, kind: str, location: str, rev: str | None
) -> None:
    parsed = parse_package_spec(text)

    assert (parsed.kind, parsed.location, parsed.rev) == (kind, location, rev)


def test_package_identity_ignores_npm_version_and_git_transport_or_ref() -> None:
    assert package_identity(parse_package_spec("npm:@scope/pkg@1.0.0")) == "npm:@scope/pkg"
    assert package_identity(parse_package_spec("npm:@scope/pkg@2.0.0")) == "npm:@scope/pkg"
    assert package_identity(parse_package_spec("git:github.com/acme/pi-kit@v1")) == (
        "git:github.com/acme/pi-kit"
    )
    assert package_identity(parse_package_spec("git:git@github.com:acme/pi-kit@v2")) == (
        "git:github.com/acme/pi-kit"
    )


@pytest.mark.parametrize(
    "text",
    ["npm:", "npm:@scope", "git:", "git:github.com/acme/pi-kit@", "https://host/repo@"],
)
def test_parse_rejects_incomplete_upstream_sources(text: str) -> None:
    with pytest.raises(PackageSpecError):
        parse_package_spec(text)
