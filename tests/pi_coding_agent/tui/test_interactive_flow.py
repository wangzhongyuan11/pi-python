from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import time
from collections.abc import Iterable
from dataclasses import replace
from io import StringIO
from pathlib import Path

import pytest
from pydantic import BaseModel

from pi_agent import Agent, AgentTool, AgentToolResult, AgentToolUpdateCallback
from pi_ai import (
    AssistantMessage,
    AssistantStream,
    Context,
    FakeProvider,
    Model,
    StreamOptions,
    TextContent,
    ToolCall,
    fake_assistant_message,
    fake_model,
)
from pi_coding_agent.agent_session import AgentSession
from pi_coding_agent.compaction.service import CompactionService
from pi_coding_agent.compaction.summarizer import CompactionSummarizer
from pi_coding_agent.deepseek_credentials import DeepSeekCredentialResolver
from pi_coding_agent.model_runtime import ModelRuntime, create_model_runtime, match_model_argument
from pi_coding_agent.services import create_product_services
from pi_coding_agent.session.manager import SessionManager
from pi_coding_agent.session.models import SessionEntry
from pi_coding_agent.tui.commands import CommandDispatcher, CommandOutcome, CommandSpec
from pi_coding_agent.tui.extension_ui import DialogBridge
from pi_coding_agent.tui.main import InteractiveApp
from pi_coding_agent.tui.runner import InteractiveOptions, SlashCompleter, run_interactive


def _session(tmp_path: Path, provider: FakeProvider) -> AgentSession:
    return AgentSession(
        agent=Agent(model=fake_model(), stream_function=provider.stream),
        session_manager=SessionManager.in_memory(
            cwd=tmp_path, session_id="tui", timestamp="2026-08-24T00:00:00Z"
        ),
        services=create_product_services(tmp_path),
    )


def _app(session: AgentSession, dispatcher: CommandDispatcher | None = None) -> InteractiveApp:
    return InteractiveApp(session=session, dispatcher=dispatcher)


def test_cjk_reply_streams_into_output_lines(tmp_path: Path) -> None:
    provider = FakeProvider([fake_assistant_message("你好，世界！")])
    app = _app(_session(tmp_path, provider))

    asyncio.run(app.handle("打个招呼"))
    screen = "".join(app.lines)

    assert "你好，世界！" in screen


def test_each_completed_turn_is_rendered_once_without_replaying_history(tmp_path: Path) -> None:
    provider = FakeProvider(
        [fake_assistant_message("first answer"), fake_assistant_message("second answer")]
    )
    app = _app(_session(tmp_path, provider))

    async def scenario() -> None:
        await app.handle("first")
        await app.handle("second")

    asyncio.run(scenario())
    screen = "\n".join(app.lines)

    assert screen.count("first answer") == 1
    assert screen.count("second answer") == 1
    assert screen.count("> first") == 1
    assert screen.count("> second") == 1


class _Args(BaseModel):
    value: str


def test_tool_turn_renders_done_row(tmp_path: Path) -> None:
    async def execute(
        _tool_call_id: str,
        params: _Args,
        _abort_event: object,
        _on_update: AgentToolUpdateCallback[dict[str, str]] | None,
    ) -> AgentToolResult[dict[str, str]]:
        return AgentToolResult(content=(TextContent(text=params.value),), details={})

    tool = AgentTool(
        name="side_effect",
        label="Side effect",
        description="records",
        parameter_type=_Args,
        execute=execute,
    )
    provider = FakeProvider(
        [
            fake_assistant_message(
                ToolCall(id="call-1", name="side_effect", arguments={"value": "x"}),
                stop_reason="toolUse",
            ),
            fake_assistant_message("finished"),
        ]
    )
    session = AgentSession(
        agent=Agent(model=fake_model(), stream_function=provider.stream, tools=(tool,)),
        session_manager=SessionManager.in_memory(
            cwd=tmp_path, session_id="tools", timestamp="2026-08-24T00:00:00Z"
        ),
        services=create_product_services(tmp_path),
    )
    app = _app(session)

    asyncio.run(app.handle("run it"))
    screen = "".join(app.lines)

    assert "side_effect: done" in screen
    assert "finished" in screen


def test_tool_failure_renders_the_error_content_summary(tmp_path: Path) -> None:
    async def execute(
        _tool_call_id: str,
        _params: _Args,
        _abort_event: object,
        _on_update: AgentToolUpdateCallback[dict[str, str]] | None,
    ) -> AgentToolResult[dict[str, str]]:
        raise RuntimeError("execvpe(/bin/bash) failed: No such file or directory")

    tool = AgentTool(
        name="bash",
        label="bash",
        description="fails",
        parameter_type=_Args,
        execute=execute,
    )
    provider = FakeProvider(
        [
            fake_assistant_message(
                ToolCall(id="call-1", name="bash", arguments={"value": "x"}),
                stop_reason="toolUse",
            ),
            fake_assistant_message("finished"),
        ]
    )
    session = AgentSession(
        agent=Agent(model=fake_model(), stream_function=provider.stream, tools=(tool,)),
        session_manager=SessionManager.in_memory(
            cwd=tmp_path, session_id="tool-error", timestamp="2026-08-24T00:00:00Z"
        ),
        services=create_product_services(tmp_path),
    )
    app = _app(session)

    asyncio.run(app.handle("run it"))
    screen = "".join(app.lines)

    assert "bash: failed (execvpe(/bin/bash) failed: No such file or directory)" in screen


def test_tool_lifecycle_emits_running_before_done(tmp_path: Path) -> None:
    observed: list[str] = []

    async def execute(
        _tool_call_id: str,
        params: _Args,
        _abort_event: object,
        _on_update: AgentToolUpdateCallback[dict[str, str]] | None,
    ) -> AgentToolResult[dict[str, str]]:
        assert any("side_effect: running" in line for line in observed)
        return AgentToolResult(content=(TextContent(text=params.value),), details={})

    tool = AgentTool(
        name="side_effect",
        label="Side effect",
        description="records",
        parameter_type=_Args,
        execute=execute,
    )
    provider = FakeProvider(
        [
            fake_assistant_message(
                ToolCall(id="call-1", name="side_effect", arguments={"value": "x"}),
                stop_reason="toolUse",
            ),
            fake_assistant_message("finished"),
        ]
    )
    session = AgentSession(
        agent=Agent(model=fake_model(), stream_function=provider.stream, tools=(tool,)),
        session_manager=SessionManager.in_memory(
            cwd=tmp_path, session_id="tool-stream", timestamp="2026-08-24T00:00:00Z"
        ),
        services=create_product_services(tmp_path),
    )
    app = InteractiveApp(session=session, sink=observed.append)

    asyncio.run(app.handle("run it"))

    assert any("side_effect: done" in line for line in app.lines)


def test_retry_recovery_is_reported_in_status_lines(tmp_path: Path) -> None:
    provider = FakeProvider(
        [
            fake_assistant_message("bad", stop_reason="error", error_message="503 overloaded"),
            fake_assistant_message("recovered answer"),
        ]
    )
    app = _app(_session(tmp_path, provider))

    asyncio.run(app.handle("try again"))
    screen = "".join(app.lines)

    assert "recovered" in screen


def test_manual_compaction_reports_activity_in_status_lines(tmp_path: Path) -> None:
    class _FixedSummarizer(CompactionSummarizer):
        async def summarize(
            self, entries: tuple[SessionEntry, ...], *, previous_summary: str | None
        ) -> str:
            return "compacted summary"

    manager = SessionManager.in_memory(
        cwd=tmp_path, session_id="compact-tui", timestamp="2026-08-24T00:00:00Z"
    )
    session = AgentSession(
        agent=Agent(model=fake_model(), stream_function=FakeProvider([]).stream),
        session_manager=manager,
        services=create_product_services(tmp_path),
        compaction_service=CompactionService(
            session_manager=manager,
            summarizer=_FixedSummarizer(),
            entry_id_factory=lambda: "compaction-1",
            timestamp_factory=lambda: "2026-08-24T00:00:01Z",
        ),
    )
    app = InteractiveApp(session=session)

    async def scenario() -> None:
        await session.prompt("hello")
        await session.compact()

    asyncio.run(scenario())
    screen = "".join(app.lines)

    assert "compacting context" in screen
    assert "compacted (was " in screen and " tokens)" in screen


def test_extension_dialog_cancel_yields_none_answer(tmp_path: Path) -> None:
    bridge = DialogBridge()

    async def approve(_args: str) -> CommandOutcome:
        answer = await bridge.show_dialog("approve?")
        return CommandOutcome(kind="message", text=f"answer={answer}")

    dispatcher = CommandDispatcher()
    dispatcher.register(CommandSpec(name="approve", source="ext", handler=approve))
    app = _app(_session(tmp_path, FakeProvider([])), dispatcher)

    async def scenario() -> str:
        task = asyncio.ensure_future(app.handle("/approve"))
        await asyncio.sleep(0.01)
        bridge.cancel_pending()
        await task
        return "".join(app.lines)

    assert "answer=None" in asyncio.run(scenario())


def test_real_interactive_loop_reads_multiple_prompts_and_exits(tmp_path: Path) -> None:
    provider = FakeProvider([fake_assistant_message("streamed answer")])
    runtime = ModelRuntime(provider=provider, model=provider.models[0])
    replies = iter(("hello", "/exit"))
    output = StringIO()
    errors = StringIO()

    async def read_line(_prompt: str) -> str | None:
        return next(replies, None)

    code = asyncio.run(
        run_interactive(
            InteractiveOptions(
                cwd=tmp_path,
                credential_resolver=DeepSeekCredentialResolver(environ={}, cwd=tmp_path),
                model_runtime=runtime,
                no_session=True,
            ),
            stdout=output,
            stderr=errors,
            read_line=read_line,
        )
    )

    assert code == 0
    assert "streamed answer" in output.getvalue()
    assert errors.getvalue() == ""


def test_real_interactive_loop_can_read_the_current_project_by_default(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("project architecture", encoding="utf-8")
    provider = FakeProvider(
        [
            fake_assistant_message(
                ToolCall(id="read-project", name="read", arguments={"path": "README.md"}),
                stop_reason="toolUse",
            ),
            fake_assistant_message("architecture explained"),
        ]
    )
    runtime = ModelRuntime(provider=provider, model=provider.models[0])
    replies = iter(("explain this project", "/exit"))
    output = StringIO()

    async def read_line(_prompt: str) -> str | None:
        return next(replies, None)

    code = asyncio.run(
        run_interactive(
            InteractiveOptions(
                cwd=tmp_path,
                credential_resolver=DeepSeekCredentialResolver(environ={}, cwd=tmp_path),
                model_runtime=runtime,
                no_session=True,
            ),
            stdout=output,
            stderr=StringIO(),
            read_line=read_line,
        )
    )

    first_context = provider.calls[0][1]
    second_context = provider.calls[1][1]
    assert code == 0
    assert first_context.tools is not None
    assert first_context.system_prompt is not None
    assert [tool.name for tool in first_context.tools] == ["read", "bash", "edit", "write"]
    assert "expert coding assistant" in first_context.system_prompt
    assert tmp_path.resolve().as_posix() in first_context.system_prompt
    assert any(
        message.role == "toolResult"
        and any(
            isinstance(block, TextContent) and "project architecture" in block.text
            for block in message.content
        )
        for message in second_context.messages
    )
    assert "architecture explained" in output.getvalue()


def test_interactive_terminal_sanitizes_provider_control_sequences(tmp_path: Path) -> None:
    provider = FakeProvider([fake_assistant_message("\x1b]52;c;stolen\x07safe answer")])
    runtime = ModelRuntime(provider=provider, model=provider.models[0])
    replies = iter(("hello", "/exit"))
    output = StringIO()

    async def read_line(_prompt: str) -> str | None:
        return next(replies, None)

    code = asyncio.run(
        run_interactive(
            InteractiveOptions(
                cwd=tmp_path,
                credential_resolver=DeepSeekCredentialResolver(environ={}, cwd=tmp_path),
                model_runtime=runtime,
                no_session=True,
            ),
            stdout=output,
            stderr=StringIO(),
            read_line=read_line,
        )
    )

    assert code == 0
    assert "\x1b]52" not in output.getvalue()
    assert "safe answer" in output.getvalue()


def test_fullscreen_mode_enters_and_restores_the_alternate_screen(tmp_path: Path) -> None:
    output = StringIO()

    async def exit_immediately(_prompt: str) -> str | None:
        return None

    code = asyncio.run(
        run_interactive(
            InteractiveOptions(
                cwd=tmp_path,
                credential_resolver=DeepSeekCredentialResolver(environ={}, cwd=tmp_path),
                model_runtime=ModelRuntime(provider=FakeProvider(), model=fake_model()),
                no_session=True,
                tui_mode="fullscreen",
            ),
            stdout=output,
            stderr=StringIO(),
            read_line=exit_immediately,
        )
    )

    assert code == 0
    assert output.getvalue() == "\x1b[?1049h\x1b[?1049l"


def test_conflicting_extension_commands_degrade_to_warning_instead_of_crashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import dataclasses

    import pi_coding_agent.tui.runner as runner_module
    from pi_coding_agent.extensions.api import ExtensionAPI
    from pi_coding_agent.services import create_product_services as _create

    api = ExtensionAPI("shadow")

    def shadow_model(_args: str) -> str:
        return "extension model"

    api.define_command("model", shadow_model)

    class _Extensions:
        registry = api.registry

    base_session = _session(tmp_path, FakeProvider([fake_assistant_message("still works")]))
    product_services = dataclasses.replace(_create(tmp_path), extensions=_Extensions())

    class _Created:
        session = base_session
        services = product_services
        model_runtime = ModelRuntime(provider=FakeProvider(), model=fake_model())

        async def __aenter__(self) -> _Created:
            return self

        async def __aexit__(self, *_exc: object) -> None:
            return None

    async def fake_create(_options: object) -> _Created:
        return _Created()

    monkeypatch.setattr(runner_module, "create_agent_session", fake_create)
    output = StringIO()
    errors = StringIO()
    replies = iter(("hello", "/exit"))

    async def read_line(_prompt: str) -> str | None:
        return next(replies, None)

    code = asyncio.run(
        runner_module.run_interactive(
            InteractiveOptions(
                cwd=tmp_path,
                credential_resolver=DeepSeekCredentialResolver(environ={}, cwd=tmp_path),
                model_runtime=ModelRuntime(provider=FakeProvider(), model=fake_model()),
                no_session=True,
            ),
            stdout=output,
            stderr=errors,
            read_line=read_line,
        )
    )

    assert code == 0
    assert "/model" in errors.getvalue()
    assert "skipped" in errors.getvalue()
    assert "still works" in output.getvalue()


def test_raw_command_outcomes_bypass_screen_blocks_and_reach_the_terminal(tmp_path: Path) -> None:
    dispatcher = CommandDispatcher()
    dispatcher.register(
        CommandSpec(
            name="rawcmd",
            source="builtin",
            handler=lambda _args: CommandOutcome(kind="raw", text="\x1b[5n"),
        )
    )
    raw: list[str] = []
    app = InteractiveApp(
        session=_session(tmp_path, FakeProvider([])), dispatcher=dispatcher, raw_sink=raw.append
    )

    asyncio.run(app.handle("/rawcmd"))

    assert raw == ["\x1b[5n"]
    assert "".join(app.lines) == ""


def test_copy_sends_last_reply_to_clipboard_over_osc52(tmp_path: Path) -> None:
    provider = FakeProvider([fake_assistant_message("copied answer")])
    runtime = ModelRuntime(provider=provider, model=provider.models[0])
    replies = iter(("hello", "/copy", "/exit"))
    output = StringIO()

    async def read_line(_prompt: str) -> str | None:
        return next(replies, None)

    code = asyncio.run(
        run_interactive(
            InteractiveOptions(
                cwd=tmp_path,
                credential_resolver=DeepSeekCredentialResolver(environ={}, cwd=tmp_path),
                model_runtime=runtime,
                no_session=True,
            ),
            stdout=output,
            stderr=StringIO(),
            read_line=read_line,
        )
    )

    expected = base64.b64encode(b"copied answer").decode("ascii")
    assert code == 0
    assert f"\x1b]52;c;{expected}\x07" in output.getvalue()


def test_copy_without_a_prior_reply_reports_nothing_to_copy(tmp_path: Path) -> None:
    runtime = ModelRuntime(provider=FakeProvider(), model=fake_model())
    replies = iter(("/copy", "/exit"))
    output = StringIO()

    async def read_line(_prompt: str) -> str | None:
        return next(replies, None)

    code = asyncio.run(
        run_interactive(
            InteractiveOptions(
                cwd=tmp_path,
                credential_resolver=DeepSeekCredentialResolver(environ={}, cwd=tmp_path),
                model_runtime=runtime,
                no_session=True,
            ),
            stdout=output,
            stderr=StringIO(),
            read_line=read_line,
        )
    )

    assert code == 0
    assert "nothing to copy" in output.getvalue()
    assert "\x1b]52" not in output.getvalue()


def _file_for_session(session_dir: Path, session_id: str) -> Path | None:
    return next(
        (path for path in session_dir.glob("*.jsonl") if path.name.endswith(f"{session_id}.jsonl")),
        None,
    )


def _persisted_user_texts(session_dir: Path) -> list[str]:
    entries: list[str] = []
    for path in sorted(session_dir.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            if record.get("type") == "message" and record.get("message", {}).get("role") == "user":
                entries.append(json.dumps(record["message"]["content"], ensure_ascii=False))
    return entries


def test_attach_sends_file_content_with_the_next_prompt_only(tmp_path: Path) -> None:
    note = tmp_path / "note.txt"
    note.write_text("file body", encoding="utf-8")
    session_dir = tmp_path / "sessions"
    provider = FakeProvider([fake_assistant_message("got it"), fake_assistant_message("again ok")])
    runtime = ModelRuntime(provider=provider, model=provider.models[0])
    replies = iter((f"/attach {note}", "use it", "plain follow up", "/exit"))
    output = StringIO()

    async def read_line(_prompt: str) -> str | None:
        return next(replies, None)

    code = asyncio.run(
        run_interactive(
            InteractiveOptions(
                cwd=tmp_path,
                credential_resolver=DeepSeekCredentialResolver(environ={}, cwd=tmp_path),
                model_runtime=runtime,
                session_dir=session_dir,
            ),
            stdout=output,
            stderr=StringIO(),
            read_line=read_line,
        )
    )

    assert code == 0
    assert "attached note.txt" in output.getvalue()
    user_texts = _persisted_user_texts(session_dir)
    assert any("file body" in text and "note.txt" in text for text in user_texts)
    assert not any("file body" in text for text in user_texts[1:])
    assert any("plain follow up" in text for text in user_texts)


def test_attach_rejects_images_for_text_only_models(tmp_path: Path) -> None:
    class _TextOnlyProvider(FakeProvider):
        @property
        def models(self):  # type: ignore[override]
            return (replace(fake_model(), input=("text",)),)

    image = tmp_path / "shot.png"
    image.write_bytes(b"\x89PNG fake")
    provider = _TextOnlyProvider()
    runtime = ModelRuntime(provider=provider, model=provider.models[0])
    replies = iter((f"/attach {image}", "/exit"))
    output = StringIO()

    async def read_line(_prompt: str) -> str | None:
        return next(replies, None)

    code = asyncio.run(
        run_interactive(
            InteractiveOptions(
                cwd=tmp_path,
                credential_resolver=DeepSeekCredentialResolver(environ={}, cwd=tmp_path),
                model_runtime=runtime,
                no_session=True,
            ),
            stdout=output,
            stderr=StringIO(),
            read_line=read_line,
        )
    )

    assert code == 0
    assert "does not support image input" in output.getvalue()


def _drive(
    tmp_path: Path,
    replies: tuple[str, ...],
    provider: FakeProvider,
    *,
    session_dir: Path | None = None,
    resume: bool = False,
) -> tuple[int, str, str]:
    runtime = ModelRuntime(provider=provider, model=provider.models[0])
    lines = iter(replies)
    output = StringIO()
    errors = StringIO()

    async def read_line(_prompt: str) -> str | None:
        return next(lines, None)

    code = asyncio.run(
        run_interactive(
            InteractiveOptions(
                cwd=tmp_path,
                credential_resolver=DeepSeekCredentialResolver(environ={}, cwd=tmp_path),
                model_runtime=runtime,
                session_dir=session_dir,
                resume=resume,
            ),
            stdout=output,
            stderr=errors,
            read_line=read_line,
        )
    )
    return code, output.getvalue(), errors.getvalue()


def test_sessions_selector_switches_the_runtime_to_the_chosen_session(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"

    first_code, _, _ = _drive(
        tmp_path,
        ("seed", "/exit"),
        FakeProvider([fake_assistant_message("seed answer")]),
        session_dir=session_dir,
    )
    assert first_code == 0
    saved = list(session_dir.glob("*.jsonl"))
    assert len(saved) == 1

    second_provider = FakeProvider([fake_assistant_message("switched answer")])
    code, output, errors = _drive(
        tmp_path,
        ("/sessions", "1", "hello", "/exit"),
        second_provider,
        session_dir=session_dir,
    )

    assert code == 0
    assert errors == ""
    match = re.search(r"switched to ([0-9a-f]{32})", output)
    assert match is not None
    switched_id = match.group(1)
    assert "1. " in output
    target = _file_for_session(session_dir, switched_id)
    assert target is not None
    content = target.read_text(encoding="utf-8")
    assert '"hello"' in content
    assert "switched answer" in content


def test_sessions_selector_cancel_keeps_the_current_session(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    _drive(
        tmp_path,
        ("seed", "/exit"),
        FakeProvider([fake_assistant_message("seed answer")]),
        session_dir=session_dir,
    )

    code, output, _ = _drive(
        tmp_path,
        ("/sessions", "", "/exit"),
        FakeProvider([]),
        session_dir=session_dir,
    )

    assert code == 0
    assert "cancelled" in output
    assert "switched to" not in output
    assert len(list(session_dir.glob("*.jsonl"))) == 1


def test_sessions_selector_defaults_to_the_per_project_session_directory(
    tmp_path: Path,
) -> None:
    _drive(tmp_path, ("seed", "/exit"), FakeProvider([fake_assistant_message("s")]))
    default_root = Path.home() / ".pi-python" / "agent" / "sessions"
    project_dirs = [path for path in default_root.glob("*") if path.is_dir()]
    assert project_dirs, "expected the first turn to create the per-project session directory"

    code, output, errors = _drive(
        tmp_path,
        ("/sessions", "1", "hello", "/exit"),
        FakeProvider([fake_assistant_message("switched answer")]),
    )

    assert code == 0
    assert errors == ""
    match = re.search(r"switched to ([0-9a-f]{32})", output)
    assert match is not None
    target = next(
        path
        for path in sorted(default_root.rglob("*.jsonl"))
        if path.name.endswith(f"{match.group(1)}.jsonl")
    )
    content = target.read_text(encoding="utf-8")
    assert '"hello"' in content


def test_interactive_resume_without_session_dir_continues_newest_session(
    tmp_path: Path,
) -> None:
    _drive(
        tmp_path,
        ("seed", "/exit"),
        FakeProvider([fake_assistant_message("seed answer")]),
    )
    default_root = Path.home() / ".pi-python" / "agent" / "sessions"
    project_dirs = [path for path in default_root.glob("*") if path.is_dir()]
    assert project_dirs, "expected the first turn to create the per-project session directory"
    before = list(default_root.rglob("*.jsonl"))
    assert len(before) == 1

    code, output, errors = _drive(
        tmp_path,
        ("hello", "/exit"),
        FakeProvider([fake_assistant_message("resumed answer")]),
        resume=True,
    )

    assert code == 0, output + errors
    assert errors == ""
    assert "resumed answer" in output
    after = list(default_root.rglob("*.jsonl"))
    assert len(after) == 1, "resume must continue the existing session, not create a new one"
    content = after[0].read_text(encoding="utf-8")
    assert '"seed"' in content
    assert '"hello"' in content


def test_fork_creates_a_child_session_and_switches_to_it(tmp_path: Path) -> None:
    session_dir = tmp_path / "sessions"
    _drive(
        tmp_path,
        ("seed", "/exit"),
        FakeProvider([fake_assistant_message("seed answer")]),
        session_dir=session_dir,
    )

    code, output, errors = _drive(
        tmp_path,
        ("second", "/fork", "/exit"),
        FakeProvider([fake_assistant_message("second answer")]),
        session_dir=session_dir,
    )

    assert code == 0
    assert errors == ""
    files = sorted(session_dir.glob("*.jsonl"))
    assert len(files) == 3
    fork_match = re.search(r"forked to ([0-9a-f]{32})", output)
    assert fork_match is not None
    child = _file_for_session(session_dir, fork_match.group(1))
    assert child is not None
    parent_candidates = [path for path in files if path != child]
    parents = [path for path in parent_candidates if "second" in path.read_text(encoding="utf-8")]
    assert len(parents) == 1
    header = json.loads(child.read_text(encoding="utf-8").splitlines()[0])
    assert header["parentSession"] == str(parents[0].resolve())


def test_regular_mode_renders_each_transcript_line_exactly_once(tmp_path: Path) -> None:
    provider = FakeProvider(
        [fake_assistant_message("first answer"), fake_assistant_message("second answer")]
    )
    runtime = ModelRuntime(provider=provider, model=provider.models[0])
    replies = iter(("first", "second", "/exit"))
    output = StringIO()

    async def read_line(_prompt: str) -> str | None:
        return next(replies, None)

    code = asyncio.run(
        run_interactive(
            InteractiveOptions(
                cwd=tmp_path,
                credential_resolver=DeepSeekCredentialResolver(environ={}, cwd=tmp_path),
                model_runtime=runtime,
                no_session=True,
            ),
            stdout=output,
            stderr=StringIO(),
            read_line=read_line,
        )
    )

    assert code == 0
    screen = output.getvalue()
    assert screen.count("> first") == 1
    assert screen.count("> second") == 1
    assert screen.count("first answer") == 1
    assert screen.count("second answer") == 1


def test_regular_mode_scrolls_long_stream_once_and_leaves_a_fresh_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pi_coding_agent.tui.runner as runner

    def terminal_size(fallback: tuple[int, int]) -> os.terminal_size:
        del fallback
        return os.terminal_size((20, 3))

    monkeypatch.setattr(
        runner.shutil,
        "get_terminal_size",
        terminal_size,
    )
    rows = tuple(f"row-{index:02}" for index in range(6))
    provider = FakeProvider(
        [fake_assistant_message("\n".join(rows))],
        chunk_size=len(rows[0]) + 1,
    )
    runtime = ModelRuntime(provider=provider, model=provider.models[0])
    replies = iter(("explain", "/exit"))
    output = StringIO()

    async def read_line(_prompt: str) -> str | None:
        return next(replies, None)

    code = asyncio.run(
        run_interactive(
            InteractiveOptions(
                cwd=tmp_path,
                credential_resolver=DeepSeekCredentialResolver(environ={}, cwd=tmp_path),
                model_runtime=runtime,
                no_session=True,
            ),
            stdout=output,
            stderr=StringIO(),
            read_line=read_line,
        )
    )

    assert code == 0
    screen = output.getvalue()
    counts = {row: screen.count(row) for row in rows}
    assert counts == {row: 1 for row in rows}
    assert all(f"{row} " not in screen for row in rows)
    assert screen.endswith("\r\n")


def test_regular_mode_reserves_the_autowrap_column(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pi_coding_agent.tui.runner as runner

    def terminal_size(fallback: tuple[int, int]) -> os.terminal_size:
        del fallback
        return os.terminal_size((20, 3))

    monkeypatch.setattr(runner.shutil, "get_terminal_size", terminal_size)
    provider = FakeProvider(
        [fake_assistant_message("12345678901234567890X")],
        chunk_size=64,
    )
    runtime = ModelRuntime(provider=provider, model=provider.models[0])
    replies = iter(("explain", "/exit"))
    output = StringIO()

    async def read_line(_prompt: str) -> str | None:
        return next(replies, None)

    code = asyncio.run(
        run_interactive(
            InteractiveOptions(
                cwd=tmp_path,
                credential_resolver=DeepSeekCredentialResolver(environ={}, cwd=tmp_path),
                model_runtime=runtime,
                no_session=True,
            ),
            stdout=output,
            stderr=StringIO(),
            read_line=read_line,
        )
    )

    assert code == 0
    assert "1234567890123456789\r\n0X" in output.getvalue()


def test_stream_terminal_writes_ansi_through_the_prompt_toolkit_output_port() -> None:
    import pi_coding_agent.tui.runner as runner

    class RecordingOutput:
        def __init__(self) -> None:
            self.raw: list[str] = []
            self.flushes = 0

        def write_raw(self, data: str) -> None:
            self.raw.append(data)

        def flush(self) -> None:
            self.flushes += 1

    stdout = StringIO()
    output_port = RecordingOutput()
    terminal = runner._StreamTerminal(  # pyright: ignore[reportPrivateUsage]
        stdout,
        fullscreen=False,
        output_port=output_port,
    )

    terminal.clear_line()

    assert output_port.raw == ["\r\x1b[K"]
    assert output_port.flushes == 1
    assert stdout.getvalue() == ""


def test_stream_terminal_forces_the_windows_vt_output_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pi_coding_agent.tui.runner as runner

    class TtyStream(StringIO):
        def isatty(self) -> bool:
            return True

    expected = object()

    def create_windows_output(_output: object) -> object:
        return expected

    monkeypatch.setattr(runner.sys, "platform", "win32")
    monkeypatch.setattr(
        runner,
        "_create_windows_output",
        create_windows_output,
        raising=False,
    )

    output_port = runner._create_output_port(TtyStream())  # pyright: ignore[reportPrivateUsage]

    assert output_port is expected


def test_streaming_updates_render_only_the_active_block_then_commit(tmp_path: Path) -> None:
    provider = FakeProvider([fake_assistant_message("流式回答内容")], chunk_size=2)
    blocks: list[tuple[str, ...]] = []
    commits: list[int] = []
    app = InteractiveApp(
        session=_session(tmp_path, provider),
        block_sink=blocks.append,
        commit_sink=lambda: commits.append(1),
    )

    asyncio.run(app.handle("你好"))

    assert all("> 你好" not in "".join(block) or block == blocks[0] for block in blocks)
    joined_blocks = {"".join(block) for block in blocks}
    assert any("流式回答" in text for text in joined_blocks)
    assert not any("> 你好" in text and "流式回答" in text for text in joined_blocks)
    assert len(commits) >= 2
    assert "流式回答内容" in "".join(app.lines)


def test_interactive_mode_clearly_rejects_macos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pi_coding_agent.tui.runner as runner

    monkeypatch.setattr(runner.sys, "platform", "darwin")
    errors = StringIO()

    code = asyncio.run(
        run_interactive(
            InteractiveOptions(
                cwd=tmp_path,
                credential_resolver=DeepSeekCredentialResolver(environ={}, cwd=tmp_path),
                model_runtime=ModelRuntime(provider=FakeProvider(), model=fake_model()),
                no_session=True,
            ),
            stdout=StringIO(),
            stderr=errors,
            read_line=lambda _prompt: asyncio.sleep(0, result=None),
        )
    )

    assert code == 2
    assert "macOS" in errors.getvalue()


def test_replay_renders_restored_history_on_interactive_resume(tmp_path: Path) -> None:
    _drive(
        tmp_path,
        ("seed", "/exit"),
        FakeProvider([fake_assistant_message("seed answer")]),
    )

    code, output, errors = _drive(
        tmp_path,
        ("hello", "/exit"),
        FakeProvider([fake_assistant_message("resumed answer")]),
        resume=True,
    )

    assert code == 0, output + errors
    assert errors == ""
    assert "seed answer" in output, "restored history must be replayed into the transcript"
    assert "> seed" in output
    assert "resumed answer" in output


class _SlowFakeProvider(FakeProvider):
    """FakeProvider whose responses arrive after a configurable delay."""

    def __init__(self, responses: Iterable[AssistantMessage], *, delay: float) -> None:
        super().__init__(responses)
        self._delay = delay

    def stream(
        self,
        model: Model,
        context: Context,
        options: StreamOptions | None = None,
    ) -> AssistantStream:
        stream = AssistantStream()
        self._calls.append((model, context))
        task = asyncio.create_task(self._slow_produce(stream, model, options))
        self._tasks.add(task)
        return stream

    async def _slow_produce(
        self,
        stream: AssistantStream,
        model: Model,
        options: StreamOptions | None,
    ) -> None:
        await asyncio.sleep(self._delay)
        aborted = (
            options is not None and options.abort_event is not None and options.abort_event.is_set()
        )
        response = self._responses.popleft() if self._responses else None
        if aborted and response is not None:
            response = replace(response, stop_reason="aborted")
        await self._produce(stream, model, response, options)


def test_input_typed_during_a_turn_is_queued_as_steering(tmp_path: Path) -> None:
    provider = _SlowFakeProvider(
        [fake_assistant_message("first reply"), fake_assistant_message("second reply")],
        delay=0.5,
    )
    runtime = ModelRuntime(provider=provider, model=provider.models[0])
    lines = iter(("start", "next", "/exit"))
    typed = iter("fix the bug please\r")
    output = StringIO()
    errors = StringIO()

    async def read_line(_prompt: str) -> str | None:
        return next(lines, None)

    def read_char() -> str | None:
        try:
            return next(typed)
        except StopIteration:
            return None

    code = asyncio.run(
        run_interactive(
            InteractiveOptions(
                cwd=tmp_path,
                credential_resolver=DeepSeekCredentialResolver(environ={}, cwd=tmp_path),
                model_runtime=runtime,
                no_session=True,
            ),
            stdout=output,
            stderr=errors,
            read_line=read_line,
            read_char=read_char,
        )
    )

    assert code == 0, output.getvalue() + errors.getvalue()
    assert errors.getvalue() == "", repr(errors.getvalue())
    assert "steered: fix the bug please" in output.getvalue()
    assert provider.call_count == 3
    steered_texts = [
        block.text
        for message in provider.calls[1][1].messages
        for block in (message.content or ())
        if isinstance(block, TextContent) and block.text == "fix the bug please"
    ]
    assert steered_texts, "steered message must reach the next model request"


def test_escape_during_a_turn_aborts_and_reports_cancellation(tmp_path: Path) -> None:
    provider = _SlowFakeProvider(
        [fake_assistant_message("long running answer")],
        delay=0.8,
    )
    runtime = ModelRuntime(provider=provider, model=provider.models[0])
    lines = iter(("go", "/exit"))
    output = StringIO()
    errors = StringIO()
    started = time.monotonic()

    async def read_line(_prompt: str) -> str | None:
        return next(lines, None)

    def read_char():
        return "\x1b" if time.monotonic() - started > 0.3 else None

    code = asyncio.run(
        run_interactive(
            InteractiveOptions(
                cwd=tmp_path,
                credential_resolver=DeepSeekCredentialResolver(environ={}, cwd=tmp_path),
                model_runtime=runtime,
                no_session=True,
            ),
            stdout=output,
            stderr=errors,
            read_line=read_line,
            read_char=read_char,
        )
    )

    assert code == 0, output.getvalue() + errors.getvalue()
    assert errors.getvalue() == "", repr(errors.getvalue())
    assert "cancelled" in output.getvalue()


def test_resume_without_prior_session_starts_fresh_with_note(tmp_path: Path) -> None:
    code, output, errors = _drive(
        tmp_path,
        ("hello", "/exit"),
        FakeProvider([fake_assistant_message("fresh answer")]),
        resume=True,
    )

    assert code == 0, output + errors
    assert "starting a new session" in errors
    assert "fresh answer" in output


def test_model_argument_supports_unique_partial_match_and_lists_alternatives(
    tmp_path: Path,
) -> None:
    class _KeyResolver:
        async def resolve(self, provider: str) -> str | None:
            return "test-key" if provider == "deepseek" else None

    runtime = create_model_runtime(credential_resolver=_KeyResolver())

    assert (
        match_model_argument(runtime, "deepseek/deepseek-v4-flash") == "deepseek/deepseek-v4-flash"
    )
    assert match_model_argument(runtime, "deepseek-v4-flash") == "deepseek/deepseek-v4-flash"
    assert match_model_argument(runtime, "pro") == "deepseek/deepseek-v4-pro"
    assert match_model_argument(runtime, "vision-exp") == "deepseek/deepseek-v4-flash-vision-exp"

    with pytest.raises(ValueError) as ambiguous:
        match_model_argument(runtime, "flash")
    assert "deepseek/deepseek-v4-flash-vision-exp" in str(ambiguous.value)
    assert "deepseek/deepseek-v4-flash," in str(ambiguous.value)

    with pytest.raises(ValueError) as unknown:
        match_model_argument(runtime, "nope")
    assert "available:" in str(unknown.value)
    assert "deepseek/deepseek-v4-flash" in str(unknown.value)


def test_slash_completer_suggests_commands_and_arguments() -> None:
    from prompt_toolkit.completion import CompleteEvent
    from prompt_toolkit.document import Document

    completer = SlashCompleter()

    def completions(text: str) -> list[str]:
        return [
            c.text for c in completer.get_completions(Document(text, len(text)), CompleteEvent())
        ]

    assert completions("/hel") == ["/help"]
    assert any(c.split(" ")[0] == "/model" for c in completions("/"))
    assert any(c.split(" ")[0] == "/thinking" for c in completions("/"))
    assert completions("/model fl") == ["deepseek/deepseek-v4-flash"]
    assert "deepseek/deepseek-v4-pro" in completions("/model ")
    assert set(completions("/thinking ")) >= {"off", "high", "max"}
    assert completions("hello") == []


def test_ctrl_c_at_idle_prompt_requires_double_press(tmp_path: Path) -> None:
    provider = FakeProvider([fake_assistant_message("answer")])
    runtime = ModelRuntime(provider=provider, model=provider.models[0])

    class Reader:
        def __init__(self) -> None:
            self.steps = 0

        async def __call__(self, _prompt: str) -> str | None:
            self.steps += 1
            if self.steps == 1:
                raise KeyboardInterrupt
            return "/exit"

    reader = Reader()
    output = StringIO()
    errors = StringIO()
    code = asyncio.run(
        run_interactive(
            InteractiveOptions(
                cwd=tmp_path,
                credential_resolver=DeepSeekCredentialResolver(environ={}, cwd=tmp_path),
                model_runtime=runtime,
                no_session=True,
            ),
            stdout=output,
            stderr=errors,
            read_line=reader,
        )
    )

    assert code == 0
    assert "press Ctrl+C again" in output.getvalue()


def test_double_ctrl_c_at_idle_prompt_exits(tmp_path: Path) -> None:
    provider = FakeProvider([])
    runtime = ModelRuntime(provider=provider, model=provider.models[0])

    async def read_line(_prompt: str) -> str | None:
        raise KeyboardInterrupt

    output = StringIO()
    errors = StringIO()
    code = asyncio.run(
        run_interactive(
            InteractiveOptions(
                cwd=tmp_path,
                credential_resolver=DeepSeekCredentialResolver(environ={}, cwd=tmp_path),
                model_runtime=runtime,
                no_session=True,
            ),
            stdout=output,
            stderr=errors,
            read_line=read_line,
        )
    )

    assert code == 130
    assert "press Ctrl+C again" in output.getvalue()
