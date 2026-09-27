"""P15.5-T07: real upstream-style TypeScript extension, zero source changes.

Installs the official TypeScript package fixture and proves in full product
conversations that the TypeScript tool, command, flag, control hook, UI
dialog, and lifecycle hook all work through the Node host without modifying
the extension source.
"""

from __future__ import annotations

import asyncio
from io import StringIO
from pathlib import Path

import pytest

from pi_ai import FakeProvider, TextContent, ToolCall, fake_assistant_message
from pi_coding_agent.cli.main import main
from pi_coding_agent.deepseek_credentials import DeepSeekCredentialResolver
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.sdk import CreateAgentSessionOptions, create_agent_session
from pi_coding_agent.services import ServiceOverrides
from pi_coding_agent.tui.runner import InteractiveOptions, run_interactive

REPO = Path(__file__).resolve().parents[3]
FIXTURE = REPO / "tests" / "fixtures" / "typescript_package"


def _runtime(provider: FakeProvider) -> ModelRuntime:
    return ModelRuntime(provider=provider, model=provider.models[0])


def _texts(messages: object) -> str:
    parts: list[str] = []
    for message in messages:  # type: ignore[union-attr]
        content = getattr(message, "content", None)
        if isinstance(content, str):
            parts.append(content)
        for block in content or ():
            if isinstance(block, TextContent):
                parts.append(block.text)
    return "\n".join(parts)


def _prepare(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    project = tmp_path / "project"
    agent_dir = tmp_path / "agent"
    project.mkdir()
    monkeypatch.setenv("PI_PYTHON_AGENT_DIR", str(agent_dir))
    stdout = StringIO()
    stderr = StringIO()
    code = main(
        ["install", str(FIXTURE), "--no-approve"],
        stdout=stdout,
        stderr=stderr,
        cwd=project,
        environ={"PI_PYTHON_AGENT_DIR": str(agent_dir)},
    )
    assert code == 0, stderr.getvalue()
    return project


def test_official_typescript_tool_runs_inside_a_real_conversation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _prepare(tmp_path, monkeypatch)
    provider = FakeProvider(
        [
            fake_assistant_message(
                ToolCall(id="o1", name="official_weather", arguments={"city": "capital"}),
                stop_reason="toolUse",
            ),
            fake_assistant_message("the report is in"),
        ]
    )

    async def scenario() -> tuple[tuple[str, ...], str]:
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=project,
                model_runtime=_runtime(provider),
                extension_flags={"official": True},
                project_trusted=True,
            )
        )
        try:
            await asyncio.wait_for(
                created.session.prompt("what is the weather in the capital?"), 60
            )
            tool_names = tuple(tool.name for tool in created.session.agent.state.tools)
            return tool_names, _texts(created.session.messages)
        finally:
            await created.close()

    tool_names, transcript = asyncio.run(scenario())
    assert "official_weather" in tool_names
    # The Node-side control hook rewrote "capital" to "Berlin" before execution.
    assert "Weather for Berlin" in transcript
    assert "official TypeScript extension" in transcript


def test_official_typescript_command_flag_and_ui_via_the_tui(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pi_tui.protocols import MemoryUI

    project = _prepare(tmp_path, monkeypatch)
    ui = MemoryUI(input_result="product ui answer")
    provider = FakeProvider([fake_assistant_message("idle")])
    replies = iter(("/official-report status", "/official-ask", "/exit"))

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
                extension_flags={"official": True},
                project_trusted=True,
                service_overrides=ServiceOverrides(ui=ui),
            ),
            stdout=output,
            stderr=errors,
            read_line=read_line,
        )
    )
    transcript = output.getvalue()
    assert exit_code == 0, errors.getvalue()
    assert "official:status flag:true" in transcript
    assert "ui:product ui answer" in transcript
    assert errors.getvalue() == ""
