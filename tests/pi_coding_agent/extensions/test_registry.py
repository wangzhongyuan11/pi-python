from __future__ import annotations

import pytest

from pi_coding_agent.extensions.api import ExtensionAPI
from pi_coding_agent.extensions.registry import (
    RegistryConflictError,
    RegistryInvalidNameError,
)


def test_duplicate_registration_within_a_kind_conflicts() -> None:
    registry = ExtensionAPI("my-ext")
    registry.define_tool("search")

    with pytest.raises(RegistryConflictError):
        registry.define_tool("search")


def test_same_name_across_different_kinds_is_allowed() -> None:
    registry = ExtensionAPI("my-ext")

    registry.define_tool("run")
    registry.define_command("run")

    assert registry.registry.lookup("tool", "run") is not None
    assert registry.registry.lookup("command", "run") is not None


def test_invalid_names_are_rejected() -> None:
    api = ExtensionAPI("my-ext")

    with pytest.raises(RegistryInvalidNameError):
        api.define_tool("")
    with pytest.raises(RegistryInvalidNameError):
        api.define_flag("verbose")
    api.define_flag("--verbose")


def test_api_records_source_and_registry_lists_registrations() -> None:
    api = ExtensionAPI("my-ext")
    api.define_tool("tool_a")
    api.define_command("cmd_b")
    api.define_flag("--dry-run")

    sources = {
        registration.name: registration.source for registration in api.registry.registrations()
    }
    kinds = sorted(registration.kind for registration in api.registry.registrations())

    assert set(sources.values()) == {"my-ext"}
    assert kinds == ["command", "flag", "tool"]


def test_shared_registry_detects_cross_extension_conflicts() -> None:
    from pi_coding_agent.extensions.registry import CapabilityRegistry

    shared = CapabilityRegistry()
    first = ExtensionAPI("ext-one", registry=shared)
    second = ExtensionAPI("ext-two", registry=shared)

    first.define_shortcut("ctrl+shift+t")

    with pytest.raises(RegistryConflictError):
        second.define_shortcut("ctrl+shift+t")


def test_registered_capabilities_keep_their_executable_payloads() -> None:
    api = ExtensionAPI("my-ext")

    def command(args: str) -> str:
        return args.upper()

    tool = object()
    provider = object()
    api.define_tool("search", tool)
    api.define_command("shout", command)
    api.define_provider("custom", provider)

    assert api.registry.lookup("tool", "search").payload is tool  # type: ignore[union-attr]
    registered_command = api.registry.lookup("command", "shout")
    assert registered_command is not None
    assert registered_command.payload is command
    assert registered_command.payload("hello") == "HELLO"  # type: ignore[operator]
    assert api.registry.lookup("provider", "custom").payload is provider  # type: ignore[union-attr]


def test_flag_values_are_dynamic_and_scoped_to_registering_extension() -> None:
    api = ExtensionAPI("my-ext")
    api.define_flag("--verbose", default=False)

    assert api.get_flag("--verbose") is False
    api.set_flag("--verbose", True)
    assert api.get_flag("--verbose") is True
