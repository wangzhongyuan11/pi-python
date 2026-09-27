from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Literal

import pytest

from pi_ai import FakeProvider
from pi_coding_agent.deepseek_credentials import DeepSeekCredentialResolver
from pi_coding_agent.extensions import (
    DefaultExtensionRuntime,
    ExtensionContextUnavailableError,
)
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.ports import ResourceRoot
from pi_coding_agent.resources.default_loader import DefaultResourceLoader
from pi_coding_agent.sdk import CreateAgentSessionOptions, create_agent_session
from pi_coding_agent.services import ServiceOverrides
from pi_coding_agent.session.manager import SessionManager
from pi_coding_agent.tui.runner import InteractiveOptions, run_interactive


def _write_extension(root: Path, name: str, source: str) -> None:
    directory = root / name
    directory.mkdir(parents=True)
    (directory / "pi-extension.json").write_text(
        json.dumps({"name": name, "version": "1.0.0", "entry": "main.py"}),
        encoding="utf-8",
    )
    (directory / "main.py").write_text(source, encoding="utf-8")


def _overrides(root: Path) -> ServiceOverrides:
    return ServiceOverrides(
        resource_roots=(ResourceRoot(kind="extension", path=root, source="explicit"),)
    )


def test_reload_invalidates_old_actions_and_rebinds_a_fresh_generation(
    tmp_path: Path,
) -> None:
    extension_root = tmp_path / "extensions"
    _write_extension(extension_root, "reloadable", "def activate(api):\n    pass\n")
    provider = FakeProvider()

    async def scenario() -> tuple[object, object]:
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=ModelRuntime(provider=provider, model=provider.models[0]),
                service_overrides=_overrides(extension_root),
            )
        )
        runtime = created.services.extensions
        assert isinstance(runtime, DefaultExtensionRuntime)
        old_actions = runtime.actions
        await runtime.reload()
        new_actions = runtime.actions
        assert new_actions.cwd == tmp_path.resolve()
        with pytest.raises(ExtensionContextUnavailableError):
            old_actions.get_session_name()
        await created.close()
        return old_actions, new_actions

    old_actions, new_actions = asyncio.run(scenario())
    assert old_actions is not new_actions


def test_session_replacement_invalidates_the_previous_generation(
    tmp_path: Path,
) -> None:
    extension_root = tmp_path / "extensions"
    _write_extension(extension_root, "replaceable", "def activate(api):\n    pass\n")
    provider = FakeProvider()

    async def scenario() -> None:
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=ModelRuntime(provider=provider, model=provider.models[0]),
                service_overrides=_overrides(extension_root),
            )
        )
        old_runtime = created.services.extensions
        assert isinstance(old_runtime, DefaultExtensionRuntime)
        old_actions = old_runtime.actions
        replacement = SessionManager.in_memory(
            cwd=tmp_path,
            session_id="replacement-session",
            timestamp="2026-09-02T00:00:00.000Z",
        )
        assert await created.new_session(replacement) is False
        new_runtime = created.services.extensions
        assert isinstance(new_runtime, DefaultExtensionRuntime)
        assert new_runtime.actions.cwd == tmp_path.resolve()
        with pytest.raises(ExtensionContextUnavailableError):
            old_actions.get_session_name()
        await created.close()

    asyncio.run(scenario())


@dataclass(frozen=True, slots=True)
class _ProbeEvent:
    type: Literal["probe"] = "probe"


def test_failed_activation_rolls_back_hooks_and_renderers(tmp_path: Path) -> None:
    marker = tmp_path / "leaked-hook.txt"
    extension_root = tmp_path / "extensions"
    _write_extension(
        extension_root,
        "broken",
        "def activate(api):\n"
        f"    api.on('probe', lambda _event: open({str(marker)!r}, 'w').write('leaked'))\n"
        "    api.define_message_renderer('broken', lambda _message: 'leaked-renderer')\n"
        "    raise RuntimeError('activation failed')\n",
    )
    resources = DefaultResourceLoader(
        agent_dir=tmp_path / "agent",
        resource_roots=(ResourceRoot(kind="extension", path=extension_root, source="explicit"),),
    )
    runtime = DefaultExtensionRuntime(cwd=tmp_path, resources=resources)

    async def scenario() -> None:
        await runtime.start()
        assert await runtime.emit(_ProbeEvent()) == ()

    asyncio.run(scenario())

    assert not marker.exists()
    assert runtime.renderers.render_message("broken", object()) is None
    assert any("activation failed" in item for item in runtime.diagnostics)


def test_reload_runs_teardown_in_reverse_activation_order(tmp_path: Path) -> None:
    marker = tmp_path / "teardown.txt"
    extension_root = tmp_path / "extensions"
    for name in ("a-first", "b-second"):
        _write_extension(
            extension_root,
            name,
            "def activate(api):\n"
            "    def teardown():\n"
            f"        with open({str(marker)!r}, 'a', encoding='utf-8') as stream:\n"
            f"            stream.write({name!r} + '\\n')\n"
            "    return teardown\n",
        )
    resources = DefaultResourceLoader(
        agent_dir=tmp_path / "agent",
        resource_roots=(ResourceRoot(kind="extension", path=extension_root, source="explicit"),),
    )
    runtime = DefaultExtensionRuntime(cwd=tmp_path, resources=resources)

    async def scenario() -> None:
        await runtime.start()
        await runtime.reload()
        await runtime.close()

    asyncio.run(scenario())

    assert marker.read_text(encoding="utf-8").splitlines() == [
        "b-second",
        "a-first",
        "b-second",
        "a-first",
    ]


def test_tui_command_context_reloads_and_dispatches_the_new_generation(
    tmp_path: Path,
) -> None:
    extension_root = tmp_path / "extensions"
    _write_extension(
        extension_root,
        "command-reload",
        "generation = 0\n"
        "def activate(api):\n"
        "    global generation\n"
        "    generation += 1\n"
        "    async def reload_self(_args, ctx):\n"
        "        await ctx.reload()\n"
        "        return 'reload-complete'\n"
        "    api.define_command('reload-self', reload_self)\n"
        "    api.define_command('generation', lambda _args, _ctx: f'generation:{generation}')\n",
    )
    provider = FakeProvider()
    replies = iter(("/reload-self", "/generation", "/exit"))

    async def read_line(_prompt: str) -> str | None:
        return next(replies, None)

    output = StringIO()
    errors = StringIO()
    exit_code = asyncio.run(
        run_interactive(
            InteractiveOptions(
                cwd=tmp_path,
                credential_resolver=DeepSeekCredentialResolver(environ={}, cwd=tmp_path),
                model_runtime=ModelRuntime(provider=provider, model=provider.models[0]),
                no_session=True,
                service_overrides=_overrides(extension_root),
            ),
            stdout=output,
            stderr=errors,
            read_line=read_line,
        )
    )

    assert exit_code == 0
    assert "reload-complete" in output.getvalue()
    assert "generation:2" in output.getvalue()
    assert errors.getvalue() == ""
