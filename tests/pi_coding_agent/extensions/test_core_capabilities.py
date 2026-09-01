from __future__ import annotations

import asyncio
import json
from io import StringIO
from pathlib import Path

from pi_ai import FakeProvider, TextContent, ToolCall, ToolResultMessage, fake_assistant_message
from pi_coding_agent.deepseek_credentials import DeepSeekCredentialResolver
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.ports import ResourceRoot
from pi_coding_agent.sdk import CreateAgentSessionOptions, create_agent_session
from pi_coding_agent.services import ServiceOverrides
from pi_coding_agent.tui.runner import InteractiveOptions, run_interactive


def _golden_extension(root: Path) -> None:
    directory = root / "core-capabilities"
    directory.mkdir(parents=True)
    (directory / "pi-extension.json").write_text(
        json.dumps({"name": "core-capabilities", "version": "1.0.0", "entry": "main.py"}),
        encoding="utf-8",
    )
    (directory / "main.py").write_text(
        "from dataclasses import replace\n"
        "from pydantic import BaseModel\n"
        "from pi_agent import AgentTool, AgentToolResult\n"
        "from pi_ai import FakeProvider, TextContent, fake_model\n\n"
        "class EchoParams(BaseModel):\n"
        "    text: str\n\n"
        "async def execute(_call_id, params, _abort, _update):\n"
        "    return AgentToolResult(\n"
        "        content=(TextContent(text=f'extension:{params.text}'),), details=None\n"
        "    )\n\n"
        "class ExtensionProvider(FakeProvider):\n"
        "    @property\n"
        "    def id(self):\n"
        "        return 'extension'\n\n"
        "    @property\n"
        "    def models(self):\n"
        "        return (replace(fake_model(), provider='extension', id='ext-model'),)\n\n"
        "def activate(api):\n"
        "    api.define_tool('extension_echo', AgentTool(\n"
        "        name='extension_echo', label='Extension echo',\n"
        "        description='Echo text through the extension',\n"
        "        parameter_type=EchoParams, execute=execute,\n"
        "    ))\n"
        "    api.define_command(\n"
        "        'extension-command', lambda args: f'command:{args}'\n"
        "    )\n"
        "    api.define_provider('extension', ExtensionProvider())\n",
        encoding="utf-8",
    )


def _overrides(root: Path) -> ServiceOverrides:
    return ServiceOverrides(
        resource_roots=(ResourceRoot(kind="extension", path=root, source="explicit"),)
    )


def test_extension_tool_is_executed_by_the_agent_and_provider_is_selectable(
    tmp_path: Path,
) -> None:
    extension_root = tmp_path / "extensions"
    _golden_extension(extension_root)
    provider = FakeProvider(
        [
            fake_assistant_message(
                ToolCall(
                    id="extension-call",
                    name="extension_echo",
                    arguments={"text": "hello"},
                ),
                stop_reason="toolUse",
            ),
            fake_assistant_message("done"),
        ]
    )
    runtime = ModelRuntime(provider=provider, model=provider.models[0])

    async def scenario() -> tuple[ToolResultMessage, str]:
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=runtime,
                service_overrides=_overrides(extension_root),
            )
        )
        await created.session.prompt("use the extension tool")
        result = next(
            message
            for message in created.session.messages
            if isinstance(message, ToolResultMessage)
        )
        selected = created.model_runtime.select_model("ext-model", provider_id="extension")
        await created.close()
        return result, f"{selected.provider}/{selected.id}"

    result, selected_model = asyncio.run(scenario())

    assert [block.text for block in result.content if isinstance(block, TextContent)] == [
        "extension:hello"
    ]
    assert selected_model == "extension/ext-model"


def test_tui_dispatches_extension_command_and_selects_extension_provider(
    tmp_path: Path,
) -> None:
    extension_root = tmp_path / "extensions"
    _golden_extension(extension_root)
    provider = FakeProvider()
    replies = iter(("/extension-command hello", "/model extension/ext-model", "/exit"))

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
    assert "command:hello" in output.getvalue()
    assert "model: extension/ext-model" in output.getvalue()
    assert errors.getvalue() == ""
