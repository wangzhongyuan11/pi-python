from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest

import pi_coding_agent
import pi_tui
from pi_coding_agent.ports import (
    InMemorySettings,
    NoopExtensionRuntime,
    NoopResourceLoader,
    NoopSessionExporter,
    ResourceDescriptor,
)
from pi_tui.protocols import MemoryUI


def test_product_port_exports_are_explicit() -> None:
    assert {
        "DefaultSessionImporter",
        "InMemorySettings",
        "NoopExtensionRuntime",
        "NoopResourceLoader",
        "NoopSessionExporter",
        "ResourceDescriptor",
        "SessionExporter",
        "SessionImporter",
        "Settings",
        "ImportResult",
        "SessionManager",
        "import_pi_session",
    } <= set(pi_coding_agent.__all__)
    assert {"MemoryUI", "NoopUI", "NotificationLevel", "UI"} <= set(pi_tui.__all__)


def test_in_memory_and_noop_product_ports_are_deterministic(tmp_path: Path) -> None:
    settings = InMemorySettings({"theme": "dark"})
    settings.set("thinking", "high")

    assert settings.get("theme") == "dark"
    assert settings.snapshot() == {"theme": "dark", "thinking": "high"}
    assert NoopResourceLoader().discover(tmp_path) == ()
    assert (
        NoopSessionExporter().export(object(), tmp_path / "unused.html")
        == (tmp_path / "unused.html").resolve()
    )


def test_noop_extension_and_memory_ui_protocols() -> None:
    async def exercise() -> None:
        runtime = NoopExtensionRuntime()
        assert await runtime.start() == ()
        await runtime.close()

        ui = MemoryUI(confirm_result=True, input_result="value", select_result="two")
        assert await ui.confirm("continue?") is True
        assert await ui.input("name") == "value"
        assert await ui.select("pick", ("one", "two")) == "two"
        ui.notify("done", level="info")
        ui.set_status("agent", "idle")
        assert ui.notifications == [("info", "done")]
        assert ui.status == {"agent": "idle"}

    asyncio.run(exercise())


def test_resource_descriptor_is_immutable_and_typed(tmp_path: Path) -> None:
    descriptor = ResourceDescriptor(
        kind="skill", name="review", path=tmp_path / "SKILL.md", source="explicit"
    )

    assert descriptor.kind == "skill"
    with pytest.raises(AttributeError):
        descriptor.name = "changed"  # type: ignore[misc]


def test_generic_tui_protocols_import_no_project_packages() -> None:
    source_path = Path(__file__).parents[2] / "src" / "pi_tui" / "protocols.py"
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}

    assert not any(name.startswith("pi_") for name in imported)
