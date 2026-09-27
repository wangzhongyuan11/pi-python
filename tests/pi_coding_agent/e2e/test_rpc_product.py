from __future__ import annotations

import asyncio
import json
import sys
from io import StringIO
from pathlib import Path

from pi_ai import FakeProvider, fake_model
from pi_coding_agent.cli.main import main
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.rpc.client import RpcClient


def test_rpc_main_dispatches_state_without_stdout_noise(tmp_path: Path) -> None:
    output = StringIO()
    errors = StringIO()
    code = main(
        ["--mode", "rpc", "--no-session", "--no-tools"],
        stdin=StringIO('not-json\n{"id":"state","type":"get_state"}\n'),
        stdout=output,
        stderr=errors,
        cwd=tmp_path,
        environ={},
        model_runtime=ModelRuntime(provider=FakeProvider(), model=fake_model()),
    )
    assert code == 0
    records = [json.loads(line) for line in output.getvalue().splitlines()]
    assert records[0]["success"] is False
    assert records[1]["id"] == "state"
    assert records[1]["data"]["sessionFile"] is None
    assert errors.getvalue() == ""


def test_rpc_real_subprocess_multiturn_and_clean_shutdown(tmp_path: Path) -> None:
    async def scenario() -> None:
        script = (
            "from pi_ai import FakeProvider,fake_assistant_message,fake_model\n"
            "from pi_coding_agent.model_runtime import ModelRuntime\n"
            "from pi_coding_agent.cli.main import main\n"
            "provider=FakeProvider([fake_assistant_message('first'),"
            "fake_assistant_message('second')])\n"
            "raise SystemExit(main(['--mode','rpc','--no-session','--no-tools'],"
            "model_runtime=ModelRuntime(provider=provider,model=fake_model())))\n"
        )
        client = await RpcClient.launch((sys.executable, "-u", "-c", script), cwd=tmp_path)
        async with client:
            state = await client.get_state()
            await client.prompt("First turn")
            while (await asyncio.wait_for(client.next_event(), 5))["type"] != "agent_end":
                pass
            await client.prompt("Second turn")
            while (await asyncio.wait_for(client.next_event(), 5))["type"] != "agent_end":
                pass
            messages = await client.request("get_messages")
            assert isinstance(messages, dict)
            assert len(messages["messages"]) == 4
            assert (await client.get_state()).session_id == state.session_id
            assert await client.request("new_session") == {"cancelled": False}
            assert (await client.get_state()).session_id != state.session_id

    asyncio.run(scenario())


def test_rpc_subprocess_extension_ui_and_activation_logs(tmp_path: Path) -> None:
    extension = tmp_path / "extension"
    extension.mkdir()
    (extension / "pi-extension.json").write_text(
        '{"name":"rpc-proof","version":"1.0.0","entry":"main.py"}', encoding="utf-8"
    )
    (extension / "main.py").write_text(
        "def activate(api):\n"
        " print('activation log must not corrupt stdout')\n"
        " async def ask(event):\n"
        "  value=await api.ui.input('Name')\n"
        "  api.ui.notify('hello:'+str(value))\n"
        " api.on('ui_prompt_start',ask)\n",
        encoding="utf-8",
    )

    async def scenario() -> None:
        script = (
            "from pathlib import Path\n"
            "from pi_ai import FakeProvider,fake_assistant_message,fake_model\n"
            "from pi_coding_agent.model_runtime import ModelRuntime\n"
            "from pi_coding_agent.cli.main import main\n"
            "from pi_coding_agent.services import ServiceOverrides\n"
            "from pi_coding_agent.ports import ResourceRoot\n"
            "provider=FakeProvider([fake_assistant_message('done')])\n"
            "raise SystemExit(main(['--mode','rpc','--no-session','--no-tools'],"
            "service_overrides=ServiceOverrides(resource_roots=(ResourceRoot("
            f"kind='extension',source='explicit',path=Path({str(extension)!r})),)),"
            "model_runtime=ModelRuntime(provider=provider,model=fake_model())))\n"
        )
        client = await RpcClient.launch((sys.executable, "-u", "-c", script), cwd=tmp_path)
        async with client:
            await client.get_state()
            await client.prompt("UI proof")
            request = await asyncio.wait_for(client.next_event(), 5)
            assert request["type"] == "extension_ui_request"
            assert request["method"] == "input"
            await client.respond_ui(str(request["id"]), value="Ada")
            notifications: list[object] = []
            while True:
                event = await asyncio.wait_for(client.next_event(), 5)
                if event.get("method") == "notify":
                    notifications.append(event["message"])
                if event["type"] == "agent_end":
                    break
            assert notifications == ["hello:Ada"]

    asyncio.run(scenario())
