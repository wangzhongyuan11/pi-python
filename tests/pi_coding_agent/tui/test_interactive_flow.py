from __future__ import annotations

import asyncio
from io import StringIO
from pathlib import Path

import pytest
from pydantic import BaseModel

from pi_agent import Agent, AgentTool, AgentToolResult, AgentToolUpdateCallback
from pi_ai import FakeProvider, TextContent, ToolCall, fake_assistant_message, fake_model
from pi_coding_agent.agent_session import AgentSession
from pi_coding_agent.deepseek_credentials import DeepSeekCredentialResolver
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.services import create_product_services
from pi_coding_agent.session.manager import SessionManager
from pi_coding_agent.tui.commands import CommandDispatcher, CommandOutcome, CommandSpec
from pi_coding_agent.tui.extension_ui import DialogBridge
from pi_coding_agent.tui.main import InteractiveApp
from pi_coding_agent.tui.runner import InteractiveOptions, run_interactive


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
