from __future__ import annotations

import asyncio
import json
from io import StringIO
from pathlib import Path

import pytest

from pi_ai import FakeProvider
from pi_coding_agent.cli import main as cli_main_module
from pi_coding_agent.cli.run import HeadlessOptions
from pi_coding_agent.extensions import (
    DefaultExtensionRuntime,
    ExtensionAPI,
    FlagState,
)
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.ports import ResourceRoot
from pi_coding_agent.resources.default_loader import DefaultResourceLoader
from pi_coding_agent.sdk import CreateAgentSessionOptions, create_agent_session
from pi_coding_agent.services import ServiceOverrides
from pi_coding_agent.tui.commands import CommandDispatcher, ShortcutDispatcher


def _flag_extension(root: Path) -> None:
    directory = root / "dynamic-flags"
    directory.mkdir(parents=True)
    (directory / "pi-extension.json").write_text(
        json.dumps({"name": "dynamic-flags", "version": "1.0.0", "entry": "main.py"}),
        encoding="utf-8",
    )
    (directory / "main.py").write_text(
        "def activate(api):\n"
        "    api.define_flag('--plan', default=False)\n"
        "    api.define_flag('--preset', value_type='string')\n",
        encoding="utf-8",
    )


def test_registered_extension_flags_claim_cli_values_and_unknown_flags_reject(
    tmp_path: Path,
) -> None:
    extension_root = tmp_path / "extensions"
    _flag_extension(extension_root)
    resources = DefaultResourceLoader(
        agent_dir=tmp_path / "agent",
        resource_roots=(ResourceRoot(kind="extension", path=extension_root, source="explicit"),),
    )
    runtime = DefaultExtensionRuntime(cwd=tmp_path, resources=resources)

    async def scenario() -> None:
        await runtime.start()
        runtime.apply_flags({"plan": True, "preset": "careful"})

    asyncio.run(scenario())

    plan = runtime.registry.lookup("flag", "--plan")
    preset = runtime.registry.lookup("flag", "--preset")
    assert plan is not None and isinstance(plan.payload, FlagState)
    assert preset is not None and isinstance(preset.payload, FlagState)
    assert plan.payload.value is True
    assert preset.payload.value == "careful"
    with pytest.raises(ValueError, match=r"unrecognized arguments: --missing"):
        runtime.apply_flags({"missing": True})


def test_cli_forwards_unclaimed_long_flags_to_the_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, bool | str] = {}

    async def fake_run(options: HeadlessOptions, **_kwargs: object) -> int:
        captured.update(options.extension_flags)
        return 0

    monkeypatch.setattr(cli_main_module, "run_headless", fake_run)
    output = StringIO()
    errors = StringIO()

    exit_code = cli_main_module.main(
        ["--plan", "--preset=careful", "do work"],
        stdout=output,
        stderr=errors,
        cwd=tmp_path,
        environ={},
    )

    assert exit_code == 0
    assert captured == {"plan": True, "preset": "careful"}
    assert errors.getvalue() == ""


def test_session_creation_applies_claimed_flags_and_rejects_unclaimed_flags(
    tmp_path: Path,
) -> None:
    extension_root = tmp_path / "extensions"
    _flag_extension(extension_root)
    provider = FakeProvider()
    model_runtime = ModelRuntime(provider=provider, model=provider.models[0])
    overrides = ServiceOverrides(
        resource_roots=(ResourceRoot(kind="extension", path=extension_root, source="explicit"),)
    )

    async def scenario() -> None:
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=model_runtime,
                service_overrides=overrides,
                extension_flags={"plan": True},
            )
        )
        extensions = created.services.extensions
        assert isinstance(extensions, DefaultExtensionRuntime)
        registration = extensions.registry.lookup("flag", "--plan")
        assert registration is not None and isinstance(registration.payload, FlagState)
        assert registration.payload.value is True
        await created.close()

        with pytest.raises(ValueError, match=r"unrecognized arguments: --missing"):
            await create_agent_session(
                CreateAgentSessionOptions(
                    cwd=tmp_path,
                    model_runtime=model_runtime,
                    service_overrides=overrides,
                    extension_flags={"missing": True},
                )
            )

    asyncio.run(scenario())


def test_extension_command_receives_current_context() -> None:
    api = ExtensionAPI("dynamic")
    seen: list[tuple[str, object]] = []
    context = object()

    def command(args: str, command_context: object) -> str:
        seen.append((args, command_context))
        return "done"

    api.define_command("inspect", command)
    dispatcher = CommandDispatcher.from_registry(api.registry, context=context)

    outcome = asyncio.run(dispatcher.dispatch("/inspect now"))

    assert outcome is not None and outcome.text == "done"
    assert seen == [("now", context)]


def test_extension_shortcut_dispatches_with_current_context() -> None:
    api = ExtensionAPI("dynamic")
    seen: list[object] = []
    context = object()

    def shortcut(shortcut_context: object) -> None:
        seen.append(shortcut_context)

    api.define_shortcut("ctrl+shift+t", shortcut)
    dispatcher = ShortcutDispatcher.from_registry(api.registry, context=context)

    handled = asyncio.run(dispatcher.dispatch("CTRL+SHIFT+T"))

    assert handled is True
    assert seen == [context]
    assert asyncio.run(dispatcher.dispatch("ctrl+q")) is False
