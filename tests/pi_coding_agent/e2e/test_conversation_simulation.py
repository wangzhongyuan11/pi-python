"""Full-conversation simulations across composition, packages, and extensions.

Phase 12-14 acceptance simulations: every scenario drives the real product
composition path with a scripted provider and exercises one continuous
conversation containing real tool execution, steering, extension hooks,
compaction, branching, session replacement, abort recovery, and RPC.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import time
from dataclasses import replace
from io import StringIO
from pathlib import Path
from typing import Any, cast

import pytest

from pi_ai import (
    AssistantMessage,
    AssistantStream,
    Context,
    FakeProvider,
    Model,
    StreamOptions,
    TextContent,
    ToolCall,
    UserMessage,
    fake_assistant_message,
)
from pi_coding_agent.cli.main import main
from pi_coding_agent.cli.run import HeadlessOptions, run_headless
from pi_coding_agent.deepseek_credentials import DeepSeekCredentialResolver
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.rpc.client import RpcClient
from pi_coding_agent.sdk import (
    CreateAgentSessionOptions,
    create_agent_session,
    default_session_dir,
)
from pi_coding_agent.session.catalog import open_session
from pi_coding_agent.session.manager import SessionManager
from pi_coding_agent.session.models import CompactionEntry
from pi_coding_agent.tui.runner import InteractiveOptions, run_interactive

REPO = Path(__file__).resolve().parents[3]
FIXTURE_PROJECT = REPO / "tests" / "fixtures" / "product_project"
GOLDEN_PACKAGE = REPO / "tests" / "fixtures" / "golden_package"

SIM_EXTENSION_MANIFEST = '{"name":"sim-extension","version":"1.0.0","entry":"main.py"}'
SIM_EXTENSION_MAIN = """from __future__ import annotations

import asyncio
import json
from pathlib import Path

from pydantic import BaseModel

from pi_agent import AgentTool, AgentToolResult
from pi_ai import TextContent

LOG_PATH = Path(__LOG_PATH__)
GATE_PATH = Path(__GATE_PATH__)


def _log(event, **data):
    record = {"event": event}
    record.update(data)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\\n")


class SimWaitArgs(BaseModel):
    text: str


async def _execute(_call_id, params, _abort, _update):
    while not GATE_PATH.exists():
        await asyncio.sleep(0.01)
    return AgentToolResult(
        content=(TextContent(text=f"sim-tool:{params.text}"),),
        details={"text": params.text},
    )


def activate(api):
    _log("activate")
    api.define_tool(
        "sim_wait",
        AgentTool(
            name="sim_wait",
            label="Sim wait",
            description="Blocks until the simulation gate appears, then echoes.",
            parameter_type=SimWaitArgs,
            execute=_execute,
        ),
    )

    def session_start(_event):
        _log("session_start")

    def turn_start(_event):
        _log("turn_start")

    def before_request(event):
        payload = dict(event.payload)
        payload["hook"] = "sim-request"
        _log("before_provider_request")
        return payload

    def before_headers(event):
        event.headers["X-Sim-Extension"] = "active"
        _log("before_provider_headers")

    def tool_call(event):
        _log("tool_call", tool=event.tool_name)
        if event.tool_name == "read":
            event.input["path"] = str(GATE_PATH)

    def tool_result(event):
        _log("tool_result", tool=event.tool_name)

    def agent_end(_event):
        _log("agent_end")

    api.on("session_start", session_start)
    api.on("turn_start", turn_start)
    api.on("before_provider_request", before_request)
    api.on("before_provider_headers", before_headers)
    api.on("tool_call", tool_call)
    api.on("tool_result", tool_result)
    api.on("agent_end", agent_end)

    async def note_command(args, context):
        context.set_session_name(f"sim-{args.strip()}")
        return "sim-noted"

    api.define_command("sim-note", note_command)

    return lambda: _log("deactivate")
"""


class HookAwareFakeProvider(FakeProvider):
    """FakeProvider that honors on_payload/transform_headers like real providers."""

    def __init__(self, responses: list[AssistantMessage], *, chunk_size: int = 4) -> None:
        super().__init__(responses, chunk_size=chunk_size)
        self.payloads: list[dict[str, object]] = []
        self.request_headers: list[dict[str, str | None]] = []

    def stream(
        self, model: Model, context: Context, options: StreamOptions | None = None
    ) -> AssistantStream:
        if options is None or options.on_payload is None or options.transform_headers is None:
            return super().stream(model, context, options)
        outer = AssistantStream()
        on_payload = options.on_payload
        transform_headers = options.transform_headers

        async def produce() -> None:
            payload = await on_payload({"marker": "original"}, model)
            self.payloads.append(cast("dict[str, object]", payload))
            headers = await transform_headers(dict(getattr(model, "headers", None) or {}), model)
            self.request_headers.append(dict(headers))
            inner = FakeProvider.stream(
                self, model, context, replace(options, on_payload=None, transform_headers=None)
            )
            async for event in inner:
                outer.push(event)

        task = asyncio.create_task(produce())
        task.add_done_callback(lambda completed: completed.exception())
        return outer


class _GatedFakeProvider(FakeProvider):
    """FakeProvider whose first stream waits on a gate, making abort deterministic."""

    def __init__(self, responses: list[AssistantMessage], *, gate: asyncio.Event) -> None:
        super().__init__(responses)
        self._gate = gate

    def stream(
        self, model: Model, context: Context, options: StreamOptions | None = None
    ) -> AssistantStream:
        outer = AssistantStream()

        async def produce() -> None:
            await self._gate.wait()
            inner = FakeProvider.stream(self, model, context, options)
            async for event in inner:
                outer.push(event)

        task = asyncio.create_task(produce())
        task.add_done_callback(lambda completed: completed.exception())
        return outer


def _runtime(provider: FakeProvider) -> ModelRuntime:
    return ModelRuntime(provider=provider, model=provider.models[0])


def _prepare_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    golden: bool = True,
    sim_extension: bool = True,
) -> tuple[Path, Path, Path, Path]:
    project = tmp_path / "project"
    agent_dir = tmp_path / "agent"
    log = tmp_path / "sim-events.jsonl"
    gate = tmp_path / "sim-gate.txt"
    shutil.copytree(FIXTURE_PROJECT, project)
    monkeypatch.setenv("PI_PYTHON_AGENT_DIR", str(agent_dir))
    if golden:
        errors = StringIO()
        code = main(
            ["install", str(GOLDEN_PACKAGE)],
            stdout=StringIO(),
            stderr=errors,
            cwd=project,
            environ={"PI_PYTHON_AGENT_DIR": str(agent_dir)},
        )
        assert code == 0, errors.getvalue()
        assert errors.getvalue() == ""
    if sim_extension:
        root = project / ".pi-python" / "extensions" / "sim-extension"
        root.mkdir(parents=True, exist_ok=True)
        (root / "pi-extension.json").write_text(SIM_EXTENSION_MANIFEST, encoding="utf-8")
        (root / "main.py").write_text(
            SIM_EXTENSION_MAIN.replace("__LOG_PATH__", json.dumps(str(log))).replace(
                "__GATE_PATH__", json.dumps(str(gate))
            ),
            encoding="utf-8",
        )
    return project, agent_dir, log, gate


def _read_log(log: Path) -> list[dict[str, Any]]:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


async def _wait_for_log(log: Path, event: str, *, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if any(record["event"] == event for record in _read_log(log)):
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"extension event {event!r} was not logged within {timeout}s")


def _texts(messages: Any) -> list[str]:
    parts: list[str] = []
    for message in messages:
        summary = getattr(message, "summary", None)
        if isinstance(summary, str):
            parts.append(summary)
        content = getattr(message, "content", None)
        if isinstance(content, str):
            parts.append(content)
            continue
        if content is None:
            continue
        for block in content:
            if isinstance(block, TextContent):
                parts.append(block.text)
    return parts


def _entry_text(item: Any) -> str:
    message = getattr(item, "message", None)
    if message is None:
        return ""
    dumped = message.model_dump(by_alias=True) if hasattr(message, "model_dump") else message
    return json.dumps(dumped, ensure_ascii=False, default=str)


async def _drain_until(client: RpcClient, event_type: str, *, timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        assert remaining > 0, f"timed out waiting for RPC event {event_type!r}"
        event = await asyncio.wait_for(client.next_event(), remaining)
        if event.get("type") == event_type:
            return event


def test_sdk_conversation_with_steering_hooks_compaction_branch_and_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, _agent_dir, log, gate = _prepare_project(tmp_path, monkeypatch)
    provider = HookAwareFakeProvider(
        [
            fake_assistant_message(
                ToolCall(id="sim-1", name="sim_wait", arguments={"text": "gate"}),
                stop_reason="toolUse",
            ),
            fake_assistant_message("turn-one-complete"),
            fake_assistant_message("## Summary\n- inspected the project gate"),
            fake_assistant_message("turn-two-after-compaction"),
        ]
    )

    async def scenario() -> None:
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=project,
                model_runtime=_runtime(provider),
                project_trusted=True,
                compaction_reserve_tokens=100,
                compaction_keep_recent_tokens=1,
                compaction_token_count=lambda _entry: 500,
            )
        )
        try:
            prompt_task = asyncio.create_task(created.session.prompt("inspect the project"))
            await _wait_for_log(log, "tool_call")
            created.session.agent.steer(
                UserMessage(content="meanwhile check the theme", timestamp=1)
            )
            gate.write_text("release", encoding="utf-8")
            await asyncio.wait_for(prompt_task, 10)

            events = _read_log(log)
            assert [record["event"] for record in events[:3]] == [
                "activate",
                "session_start",
                "turn_start",
            ]
            assert any(
                record["event"] == "tool_call" and record.get("tool") == "sim_wait"
                for record in events
            )
            assert any(
                record["event"] == "tool_result" and record.get("tool") == "sim_wait"
                for record in events
            )
            assert provider.payloads[0]["hook"] == "sim-request"
            assert provider.request_headers[0]["X-Sim-Extension"] == "active"

            second_request = provider.calls[1][1].messages
            second_texts = _texts(second_request)
            assert "sim-tool:gate" in second_texts
            assert "meanwhile check the theme" in second_texts
            assert second_texts.index("sim-tool:gate") < second_texts.index(
                "meanwhile check the theme"
            )

            persisted = created.session.messages
            # The golden extension's session_start hook appended its CustomMessage first.
            assert [type(message).__name__ for message in persisted] == [
                "CustomMessage",
                "UserMessage",
                "AssistantMessage",
                "ToolResultMessage",
                "UserMessage",
                "AssistantMessage",
            ]
            assert _texts(persisted)[-1] == "turn-one-complete"

            entry = await created.session.compact(custom_instructions="keep the tool trail")
            assert isinstance(entry, CompactionEntry)
            assert entry.summary == "## Summary\n- inspected the project gate"
            assert provider.call_count == 3

            await created.session.prompt("what changed?")
            fourth_texts = _texts(provider.calls[3][1].messages)
            assert any("inspected the project gate" in text for text in fourth_texts)
            assert not any("inspect the project" in text for text in fourth_texts)
            assert _texts(created.session.messages)[-1] == "turn-two-after-compaction"

            first_reply = next(
                item
                for item in created.session.session_manager.entries
                if "turn-one-complete" in _entry_text(item)
            )
            await created.session.branch(first_reply.id)
            assert _texts(created.session.messages)[-1] == "turn-one-complete"
            assert "turn-two-after-compaction" not in _texts(created.session.messages)

            replacement = SessionManager.create(
                cwd=project,
                session_dir=default_session_dir(project),
                session_id="replacement-session",
                timestamp="2026-09-26T00:00:00.000Z",
            )
            assert await created.new_session(replacement) is False
            # The replacement session starts empty; the re-activated golden
            # extension immediately appends its session_start CustomMessage.
            assert [type(message).__name__ for message in created.session.messages] == [
                "CustomMessage"
            ]
            tool_names = {tool.name for tool in created.session.agent.state.tools}
            assert {"read", "ls", "golden_echo", "sim_wait"} <= tool_names

            refreshed = [record["event"] for record in _read_log(log)]
            assert refreshed.count("activate") == 2
            assert refreshed.count("session_start") == 2
            assert refreshed.index("deactivate") < refreshed.index("activate", 1)
        finally:
            await created.close()

    asyncio.run(scenario())


def test_sdk_abort_mid_stream_then_continue_the_same_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, _agent_dir, _log, _gate = _prepare_project(
        tmp_path, monkeypatch, golden=False, sim_extension=False
    )
    stream_gate = asyncio.Event()
    provider = _GatedFakeProvider(
        [fake_assistant_message("aborted-stream " * 60)], gate=stream_gate
    )

    async def scenario() -> tuple[AssistantMessage | None, list[str]]:
        created = await create_agent_session(
            CreateAgentSessionOptions(cwd=project, model_runtime=_runtime(provider))
        )
        try:
            prompt_task = asyncio.create_task(created.session.prompt("start a long answer"))
            deadline = time.monotonic() + 10
            while not created.session.agent.state.is_streaming and time.monotonic() < deadline:
                await asyncio.sleep(0.01)
            created.session.abort()
            stream_gate.set()
            await asyncio.wait_for(prompt_task, 10)
            await created.session.wait_for_idle()
            aborted = created.session.messages[-1] if created.session.messages else None
            provider.append_responses([fake_assistant_message("recovered-after-abort")])
            await created.session.prompt("try again")
            return aborted if isinstance(aborted, AssistantMessage) else None, _texts(
                created.session.messages
            )
        finally:
            await created.close()

    aborted, final_texts = asyncio.run(scenario())
    assert aborted is not None and aborted.stop_reason == "aborted"
    assert final_texts[-1] == "recovered-after-abort"


def test_headless_conversation_then_sdk_resume_shares_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, _agent_dir, _log, _gate = _prepare_project(
        tmp_path, monkeypatch, golden=False, sim_extension=False
    )
    provider = HookAwareFakeProvider(
        [
            fake_assistant_message(
                ToolCall(
                    id="headless-1",
                    name="read",
                    arguments={"path": ".pi-python/settings.json"},
                ),
                stop_reason="toolUse",
            ),
            fake_assistant_message("The theme is fixture-theme"),
            fake_assistant_message("resumed: the theme is still fixture-theme"),
        ]
    )
    output = StringIO()
    errors = StringIO()
    code = asyncio.run(
        run_headless(
            HeadlessOptions(
                cwd=project,
                prompt="read the settings file and report the theme",
                mode="text",
                credential_resolver=DeepSeekCredentialResolver(environ={}, cwd=project),
                model_runtime=_runtime(provider),
                project_trusted=True,
            ),
            stdout=output,
            stderr=errors,
        )
    )
    assert code == 0, errors.getvalue()
    assert "The theme is fixture-theme" in output.getvalue()
    assert errors.getvalue() == ""
    session_files = list(default_session_dir(project).glob("*.jsonl"))
    assert len(session_files) == 1
    persisted = session_files[0].read_text(encoding="utf-8")
    assert "read the settings file and report the theme" in persisted
    assert "fixture-theme" in persisted

    manager = open_session(session_files[0])

    async def resume() -> tuple[list[str], list[str]]:
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=project,
                model_runtime=_runtime(provider),
                session_manager=manager,
                project_trusted=True,
            )
        )
        try:
            await created.session.prompt("and the tool result?")
            return _texts(created.session.messages), _texts(provider.calls[-1][1].messages)
        finally:
            await created.close()

    resumed_texts, request_texts = asyncio.run(resume())
    assert "resumed: the theme is still fixture-theme" in resumed_texts
    assert "read the settings file and report the theme" in request_texts
    assert "The theme is fixture-theme" in request_texts


def test_tui_conversation_with_real_tool_and_project_skill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, _agent_dir, _log, _gate = _prepare_project(
        tmp_path, monkeypatch, golden=False, sim_extension=False
    )
    provider = HookAwareFakeProvider(
        [
            fake_assistant_message(
                ToolCall(
                    id="tui-1",
                    name="read",
                    arguments={"path": ".pi-python/settings.json"},
                ),
                stop_reason="toolUse",
            ),
            fake_assistant_message("The theme is fixture-theme"),
            fake_assistant_message("Skill instructions received."),
        ]
    )
    replies = iter(
        (
            "read the settings file",
            "/skill:fixture-skill acknowledge the fixture",
            "/exit",
        )
    )

    async def read_line(_prompt: str) -> str | None:
        return next(replies, None)

    output = StringIO()
    errors = StringIO()
    exit_code = asyncio.run(
        run_interactive(
            InteractiveOptions(
                cwd=project,
                credential_resolver=DeepSeekCredentialResolver(environ={}, cwd=project),
                model_runtime=_runtime(provider),
                project_trusted=True,
            ),
            stdout=output,
            stderr=errors,
            read_line=read_line,
        )
    )
    transcript = output.getvalue()
    assert exit_code == 0
    assert "The theme is fixture-theme" in transcript
    assert "Skill instructions received." in transcript
    assert errors.getvalue() == ""
    assert provider.call_count == 3
    assert any("fixture-theme" in text for text in _texts(provider.calls[1][1].messages))
    skill_texts = _texts(provider.calls[2][1].messages)
    assert any("# Fixture skill" in text for text in skill_texts)
    assert any("Use the same product composition path." in text for text in skill_texts)


def test_rpc_conversation_with_real_tool_tree_and_fork(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, agent_dir, _log, _gate = _prepare_project(
        tmp_path, monkeypatch, golden=False, sim_extension=False
    )
    (project / "hello.txt").write_text("rpc-file-content", encoding="utf-8")
    child = (
        "import os\n"
        f"os.environ['PI_PYTHON_AGENT_DIR'] = {json.dumps(str(agent_dir))}\n"
        "from pi_ai import FakeProvider, ToolCall, fake_assistant_message, fake_model\n"
        "from pi_coding_agent.model_runtime import ModelRuntime\n"
        "from pi_coding_agent.cli.main import main\n"
        "provider = FakeProvider([\n"
        "    fake_assistant_message(\n"
        "        ToolCall(id='rpc-1', name='read', arguments={'path': 'hello.txt'}),\n"
        "        stop_reason='toolUse',\n"
        "    ),\n"
        "    fake_assistant_message('rpc-read-done'),\n"
        "    fake_assistant_message('rpc-still-here'),\n"
        "])\n"
        "raise SystemExit(main(\n"
        "    ['--mode', 'rpc', '--tools', 'read'],\n"
        "    model_runtime=ModelRuntime(provider=provider, model=fake_model()),\n"
        "))\n"
    )

    async def scenario() -> tuple[list[dict], dict[str, object], object, object, object]:
        client = await RpcClient.launch((sys.executable, "-u", "-c", child), cwd=project)
        async with client:
            state_before = await client.get_state()
            await client.prompt("read hello.txt")
            await _drain_until(client, "agent_end")
            messages = await client.request("get_messages")
            assert isinstance(messages, dict)
            turn_one = cast("list[dict]", messages["messages"])
            assert len(turn_one) == 4
            await client.request("set_thinking_level", level="off")
            tree = await client.request("get_tree")
            assert isinstance(tree, dict)
            forked = await client.request("clone")
            assert isinstance(forked, dict)
            state_after = await client.get_state()
            await client.prompt("still there?")
            await _drain_until(client, "agent_end")
            last = await client.request("get_last_assistant_text")
            assert isinstance(last, dict)
            return (
                turn_one,
                tree,
                state_before.session_id,
                state_after.session_id,
                last["text"],
            )

    turn_one, tree, session_before, session_after, last_text = asyncio.run(scenario())
    assert [record["role"] for record in turn_one] == [
        "user",
        "assistant",
        "toolResult",
        "assistant",
    ]
    turn_one_serialized = json.dumps(turn_one)
    assert "hello.txt" in turn_one_serialized
    assert "rpc-file-content" in turn_one_serialized
    assert "rpc-read-done" in turn_one_serialized
    assert tree["leafId"] is not None
    assert session_after != session_before
    assert last_text == "rpc-still-here"
