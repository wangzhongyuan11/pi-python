from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import replace
from io import StringIO
from pathlib import Path
from typing import Any, cast

import pytest

from pi_ai import (
    FakeProvider,
    Model,
    TextContent,
    ToolCall,
    UserMessage,
    fake_assistant_message,
    fake_model,
)
from pi_coding_agent.deepseek_credentials import DeepSeekCredentialResolver
from pi_coding_agent.extensions import DefaultExtensionRuntime, ExtensionAPI, ExtensionExecResult
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.ports import ResourceRoot
from pi_coding_agent.sdk import CreateAgentSessionOptions, create_agent_session
from pi_coding_agent.services import ServiceOverrides
from pi_coding_agent.session.models import (
    CustomEntry,
    CustomMessageEntry,
    LabelEntry,
    ModelChangeEntry,
    SessionInfoEntry,
    ThinkingLevelChangeEntry,
)
from pi_coding_agent.tui.runner import InteractiveOptions, run_interactive


class _TwoModelFakeProvider(FakeProvider):
    @property
    def models(self) -> tuple[Model, ...]:
        return (fake_model(), replace(fake_model(), id="fake-2", name="Fake Model 2"))


def test_api_does_not_expose_action_binding_lifecycle() -> None:
    api = ExtensionAPI("bounded-actions")

    for name in ("bind", "invalidate", "actions"):
        with pytest.raises(AttributeError):
            getattr(api, name)


def _actions_extension(root: Path) -> None:
    directory = root / "actions"
    directory.mkdir(parents=True)
    (directory / "pi-extension.json").write_text(
        json.dumps({"name": "actions", "version": "1.0.0", "entry": "main.py"}),
        encoding="utf-8",
    )
    (directory / "main.py").write_text(
        "from pydantic import BaseModel\n"
        "from pi_agent import AgentTool, AgentToolResult\n"
        "from pi_ai import TextContent\n\n"
        "class EmptyParams(BaseModel):\n"
        "    pass\n\n"
        "async def enable(_call_id, _params, _abort, _update):\n"
        "    return AgentToolResult(\n"
        "        content=(TextContent(text='enabled'),), details=None,\n"
        "        added_tool_names=('missing_tool', 'deferred_tool'),\n"
        "    )\n\n"
        "async def deferred(_call_id, _params, _abort, _update):\n"
        "    return AgentToolResult(\n"
        "        content=(TextContent(text='deferred-ran'),), details=None\n"
        "    )\n\n"
        "def activate(api):\n"
        "    api.define_tool('enable_deferred', AgentTool(\n"
        "        name='enable_deferred', label='Enable deferred',\n"
        "        description='Enable a deferred tool', parameter_type=EmptyParams,\n"
        "        execute=enable,\n"
        "    ))\n"
        "    api.define_tool('deferred_tool', AgentTool(\n"
        "        name='deferred_tool', label='Deferred tool',\n"
        "        description='Run after incremental activation', parameter_type=EmptyParams,\n"
        "        execute=deferred,\n"
        "    ))\n"
        "    def session_start(_event):\n"
        "        api.set_active_tools(['enable_deferred'])\n"
        "        name_entry = api.set_session_name('extension actions')\n"
        "        api.set_label(name_entry, 'extension-start')\n"
        "        api.set_model('fake/fake-2')\n"
        "        api.set_thinking_level('low')\n"
        "        api.append_entry('actions-ready', {\n"
        "            'active': list(api.get_active_tools()),\n"
        "            'all': [tool.name for tool in api.get_all_tools()],\n"
        "            'sources': {tool.name: tool.source for tool in api.get_all_tools()},\n"
        "            'commands': [item.name for item in api.get_commands()],\n"
        "            'cwd': str(api.cwd),\n"
        "            'idle': api.is_idle(),\n"
        "            'model': api.model.id,\n"
        "            'pending': api.has_pending_messages(),\n"
        "            'prompt': bool(api.get_system_prompt()),\n"
        "            'signal': api.signal is None,\n"
        "            'trusted': api.is_project_trusted(),\n"
        "            'usage_window': api.get_context_usage().context_window,\n"
        "        })\n"
        "        api.send_message('extension-notice', 'actions ready')\n"
        "    api.on('session_start', session_start)\n"
        "    api.define_command('send-user-action', api.send_user_message)\n"
        "    api.define_command(\n"
        "        'send-custom-turn',\n"
        "        lambda _args: api.send_message(\n"
        "            'turn-notice', 'triggered custom', trigger_turn=True\n"
        "        ),\n"
        "    )\n"
        "    async def exec_action(_args):\n"
        "        return await api.exec('fake-command', ['arg'], timeout=2)\n"
        "    api.define_command('exec-action', exec_action)\n"
        "    api.define_command('shutdown-action', lambda _args: api.shutdown())\n",
        encoding="utf-8",
    )


def test_actions_and_deferred_tool_metadata_change_the_live_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    extension_root = tmp_path / "extensions"
    _actions_extension(extension_root)
    exec_calls: list[tuple[str, tuple[str, ...], Path, float | None]] = []

    async def fake_exec(
        command: str,
        args: tuple[str, ...],
        *,
        cwd: Path,
        timeout: float | None,
        processes: set[object] | None = None,
    ) -> ExtensionExecResult:
        exec_calls.append((command, args, cwd, timeout))
        return ExtensionExecResult(stdout="exec-output", stderr="", code=0, killed=False)

    monkeypatch.setattr("pi_coding_agent.extensions.context._exec_command", fake_exec)
    provider = _TwoModelFakeProvider(
        [
            fake_assistant_message(
                ToolCall(id="enable", name="enable_deferred", arguments={}),
                stop_reason="toolUse",
            ),
            fake_assistant_message(
                ToolCall(id="deferred", name="deferred_tool", arguments={}),
                stop_reason="toolUse",
            ),
            fake_assistant_message("done"),
        ]
    )

    async def scenario():  # type: ignore[no-untyped-def]
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=ModelRuntime(provider=provider, model=provider.models[0]),
                service_overrides=ServiceOverrides(
                    resource_roots=(
                        ResourceRoot(kind="extension", path=extension_root, source="explicit"),
                    )
                ),
            )
        )
        await created.session.prompt("activate and use the deferred tool")
        runtime = created.services.extensions
        assert isinstance(runtime, DefaultExtensionRuntime)
        registration = runtime.registry.lookup("command", "send-user-action")
        assert registration is not None
        send_user = cast("Callable[[str], asyncio.Task[None]]", registration.payload)
        custom_registration = runtime.registry.lookup("command", "send-custom-turn")
        assert custom_registration is not None
        send_custom = cast("Callable[[str], asyncio.Task[None]]", custom_registration.payload)
        exec_registration = runtime.registry.lookup("command", "exec-action")
        assert exec_registration is not None
        exec_action = cast("Callable[[str], object]", exec_registration.payload)
        exec_result = await cast("Any", exec_action(""))
        provider.append_responses((fake_assistant_message("sent by action"),))
        await send_user("follow up from extension")
        provider.append_responses((fake_assistant_message("custom turn complete"),))
        await send_custom("")
        tool_names = tuple(
            tuple(tool.name for tool in (context.tools or ())) for _model, context in provider.calls
        )
        entries = created.session.session_manager.entries
        first_context = provider.calls[0][1]
        last_context = provider.calls[-1][1]
        model_ids = tuple(model.id for model, _context in provider.calls)
        thinking_level = created.session.state.thinking_level
        await created.close()
        return (
            tool_names,
            entries,
            thinking_level,
            first_context,
            last_context,
            model_ids,
            exec_result,
        )

    (
        tool_names,
        entries,
        thinking_level,
        first_context,
        last_context,
        model_ids,
        exec_result,
    ) = asyncio.run(scenario())

    assert tool_names == (
        ("enable_deferred",),
        ("enable_deferred", "deferred_tool"),
        ("enable_deferred", "deferred_tool"),
        ("enable_deferred", "deferred_tool"),
        ("enable_deferred", "deferred_tool"),
    )
    session_info = next(entry for entry in entries if isinstance(entry, SessionInfoEntry))
    label = next(entry for entry in entries if isinstance(entry, LabelEntry))
    custom = next(entry for entry in entries if isinstance(entry, CustomEntry))
    assert session_info.name == "extension actions"
    assert label.target_id == session_info.id
    assert label.label == "extension-start"
    assert custom.custom_type == "actions-ready"
    assert custom.data == {
        "active": ["enable_deferred"],
        "all": [
            "read",
            "bash",
            "edit",
            "write",
            "grep",
            "find",
            "ls",
            "deferred_tool",
            "enable_deferred",
        ],
        "commands": [
            "exec-action",
            "send-custom-turn",
            "send-user-action",
            "shutdown-action",
        ],
        "cwd": str(tmp_path.resolve()),
        "idle": True,
        "model": "fake-2",
        "pending": False,
        "prompt": True,
        "signal": True,
        "sources": {
            "read": "builtin",
            "bash": "builtin",
            "edit": "builtin",
            "write": "builtin",
            "grep": "builtin",
            "find": "builtin",
            "ls": "builtin",
            "deferred_tool": "actions",
            "enable_deferred": "actions",
        },
        "trusted": False,
        "usage_window": 128_000,
    }
    notice = next(entry for entry in entries if isinstance(entry, CustomMessageEntry))
    turn_notice = next(
        entry
        for entry in entries
        if isinstance(entry, CustomMessageEntry) and entry.custom_type == "turn-notice"
    )
    model_change = next(entry for entry in entries if isinstance(entry, ModelChangeEntry))
    thinking_change = next(
        entry for entry in entries if isinstance(entry, ThinkingLevelChangeEntry)
    )
    assert notice.custom_type == "extension-notice"
    assert notice.content == "actions ready"
    assert turn_notice.content == "triggered custom"
    assert any(
        isinstance(message, UserMessage)
        and [block.text for block in message.content if isinstance(block, TextContent)]
        == ["actions ready"]
        for message in first_context.messages
    )
    user_texts = [
        block.text
        for message in last_context.messages
        if isinstance(message, UserMessage)
        for block in message.content
        if isinstance(block, TextContent)
    ]
    assert "follow up from extension" in user_texts
    assert user_texts.count("triggered custom") == 1
    assert model_change.model_id == "fake-2"
    assert thinking_change.thinking_level == "low"
    assert model_ids == ("fake-2", "fake-2", "fake-2", "fake-2", "fake-2")
    assert thinking_level == "low"
    assert exec_result == ExtensionExecResult(stdout="exec-output", stderr="", code=0, killed=False)
    assert exec_calls == [("fake-command", ("arg",), tmp_path.resolve(), 2)]


def test_shutdown_action_exits_the_real_tui_loop(tmp_path: Path) -> None:
    extension_root = tmp_path / "extensions"
    _actions_extension(extension_root)
    reads = 0

    async def read_line(_prompt: str) -> str | None:
        nonlocal reads
        reads += 1
        if reads > 1:
            raise AssertionError("TUI requested more input after extension shutdown")
        return "/shutdown-action"

    exit_code = asyncio.run(
        run_interactive(
            InteractiveOptions(
                cwd=tmp_path,
                no_session=True,
                model_runtime=ModelRuntime(provider=_TwoModelFakeProvider(), model=fake_model()),
                credential_resolver=DeepSeekCredentialResolver(environ={}, cwd=tmp_path),
                service_overrides=ServiceOverrides(
                    resource_roots=(
                        ResourceRoot(kind="extension", path=extension_root, source="explicit"),
                    )
                ),
            ),
            stdout=StringIO(),
            stderr=StringIO(),
            read_line=read_line,
        )
    )

    assert exit_code == 0
    assert reads == 1
