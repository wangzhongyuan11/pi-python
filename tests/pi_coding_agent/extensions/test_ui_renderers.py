from __future__ import annotations

import asyncio
import json
from io import StringIO
from pathlib import Path

from pi_ai import FakeProvider
from pi_coding_agent.deepseek_credentials import DeepSeekCredentialResolver
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.ports import ResourceRoot
from pi_coding_agent.services import ServiceOverrides
from pi_coding_agent.tui.runner import InteractiveOptions, run_interactive
from pi_tui import MemoryUI


def _ui_extension(root: Path) -> None:
    directory = root / "ui-renderers"
    directory.mkdir(parents=True)
    (directory / "pi-extension.json").write_text(
        json.dumps({"name": "ui-renderers", "version": "1.0.0", "entry": "main.py"}),
        encoding="utf-8",
    )
    (directory / "main.py").write_text(
        "def activate(api):\n"
        "    api.define_message_renderer(\n"
        "        'notice', lambda message: f'rendered:{message.content}'\n"
        "    )\n"
        "    api.define_entry_renderer(\n"
        "        'panel', lambda entry: f'entry:{entry.data[\"state\"]}'\n"
        "    )\n"
        "    api.define_markdown_transformer(lambda text: text.replace('plain', 'styled'))\n"
        "    def started(_event):\n"
        "        api.send_message('notice', 'extension-ready')\n"
        "        api.append_entry('panel', {'state': 'ready'})\n"
        "    api.on('session_start', started)\n"
        "    def inspect(args, _ctx):\n"
        "        api.ui.notify(f'ui:{args}')\n"
        "        api.auth.store_secret('demo', args)\n"
        "        return 'credential-stored' if api.auth.read_secret('demo') == args else 'failed'\n"
        "    api.define_command('inspect-ui', inspect)\n",
        encoding="utf-8",
    )


def test_extension_ui_auth_and_message_renderer_reach_the_real_tui_path(
    tmp_path: Path,
) -> None:
    extension_root = tmp_path / "extensions"
    _ui_extension(extension_root)
    ui = MemoryUI()
    provider = FakeProvider()
    replies = iter(("/inspect-ui private-value", "/exit"))

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
                service_overrides=ServiceOverrides(
                    ui=ui,
                    resource_roots=(
                        ResourceRoot(kind="extension", path=extension_root, source="explicit"),
                    ),
                ),
            ),
            stdout=output,
            stderr=errors,
            read_line=read_line,
        )
    )

    assert exit_code == 0
    assert "rendered:extension-ready" in output.getvalue()
    assert "entry:ready" in output.getvalue()
    assert "credential-stored" in output.getvalue()
    assert ui.notifications == [("info", "ui:private-value")]
    assert errors.getvalue() == ""


def test_renderer_registry_supports_tool_entry_and_markdown_surfaces() -> None:
    from pi_coding_agent.extensions import ExtensionAPI, ExtensionRendererRegistry

    renderers = ExtensionRendererRegistry()
    api = ExtensionAPI("rendering", renderers=renderers)
    api.define_tool_renderer(
        "echo",
        render_call=lambda payload: f"call:{payload}",
        render_result=lambda payload: f"result:{payload}",
    )
    api.define_entry_renderer("checkpoint", lambda payload: f"entry:{payload}")
    api.define_markdown_transformer(lambda markdown: markdown.upper())

    assert renderers.render_tool_call("echo", "hello") == "call:hello"
    assert renderers.render_tool_result("echo", "done") == "result:done"
    assert renderers.render_entry("checkpoint", "saved") == "entry:saved"
    assert renderers.transform_markdown("mixed") == "MIXED"
