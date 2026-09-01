from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import cast

from pi_ai import FakeProvider, fake_assistant_message
from pi_coding_agent.extensions.runtime import DefaultExtensionRuntime
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.ports import ResourceRoot
from pi_coding_agent.sdk import CreateAgentSessionOptions, create_agent_session
from pi_coding_agent.services import ServiceOverrides


def _event_extension(root: Path, log_path: Path) -> None:
    directory = root / "event-observer"
    directory.mkdir(parents=True)
    (directory / "pi-extension.json").write_text(
        json.dumps({"name": "event-observer", "version": "1.0.0", "entry": "main.py"}),
        encoding="utf-8",
    )
    (directory / "main.py").write_text(
        "import json\n"
        "from pathlib import Path\n\n"
        f"LOG = Path({str(log_path)!r})\n\n"
        "def record(event):\n"
        "    message = getattr(event, 'message', None)\n"
        "    item = {\n"
        "        'type': event.type,\n"
        "        'role': getattr(message, 'role', None),\n"
        "        'turn_index': getattr(event, 'turn_index', None),\n"
        "    }\n"
        "    with LOG.open('a', encoding='utf-8') as stream:\n"
        "        stream.write(json.dumps(item) + '\\n')\n\n"
        "def boom(_event):\n"
        "    raise RuntimeError('extension observer failed')\n\n"
        "def activate(api):\n"
        "    for name in (\n"
        "        'ui_prompt_start', 'agent_start', 'turn_start',\n"
        "        'message_start', 'message_update', 'message_end',\n"
        "        'turn_end', 'agent_end', 'agent_settled', 'ui_prompt_end',\n"
        "    ):\n"
        "        if name == 'turn_start':\n"
        "            api.on(name, boom)\n"
        "        api.on(name, record)\n",
        encoding="utf-8",
    )


def test_agent_lifecycle_events_are_ordered_and_handler_errors_are_isolated(
    tmp_path: Path,
) -> None:
    extension_root = tmp_path / "extensions"
    log_path = tmp_path / "events.jsonl"
    _event_extension(extension_root, log_path)
    provider = FakeProvider([fake_assistant_message("answer")], chunk_size=100)

    async def scenario() -> tuple[list[str], tuple[str, ...]]:
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
        await created.session.prompt("hello")
        diagnostics = cast("DefaultExtensionRuntime", created.services.extensions).diagnostics
        await created.close()
        records = [json.loads(line) for line in log_path.read_text().splitlines()]
        assert [item["role"] for item in records if item["type"] == "message_end"] == [
            "user",
            "assistant",
        ]
        assert [item["turn_index"] for item in records if item["type"] == "turn_start"] == [0]
        assert [item["turn_index"] for item in records if item["type"] == "turn_end"] == [0]
        return [item["type"] for item in records], diagnostics

    event_types, diagnostics = asyncio.run(scenario())

    assert "message_update" in event_types
    assert [item for item in event_types if item != "message_update"] == [
        "ui_prompt_start",
        "agent_start",
        "turn_start",
        "message_start",
        "message_end",
        "message_start",
        "message_end",
        "turn_end",
        "agent_end",
        "agent_settled",
        "ui_prompt_end",
    ]
    assert any(
        "turn_start handler failed: extension observer failed" in item for item in diagnostics
    )
