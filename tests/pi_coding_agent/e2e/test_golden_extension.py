from __future__ import annotations

import asyncio
from io import StringIO
from pathlib import Path

import pytest

from pi_ai import FakeProvider, TextContent, ToolCall, UserMessage, fake_assistant_message
from pi_coding_agent.cli.main import main
from pi_coding_agent.deepseek_credentials import DeepSeekCredentialResolver
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.tui.runner import InteractiveOptions, run_interactive


def test_installed_golden_extension_survives_restart_reload_and_session_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = Path(__file__).resolve().parents[3]
    package = repository / "tests" / "fixtures" / "golden_package"
    project = tmp_path / "project"
    agent_dir = tmp_path / "agent"
    session_dir = tmp_path / "sessions"
    project.mkdir()
    environ = {"PI_PYTHON_AGENT_DIR": str(agent_dir)}
    monkeypatch.setenv("PI_PYTHON_AGENT_DIR", str(agent_dir))
    install_out = StringIO()
    install_err = StringIO()

    assert (
        main(
            ["install", str(package)],
            stdout=install_out,
            stderr=install_err,
            cwd=project,
            environ=environ,
        )
        == 0
    )
    assert install_err.getvalue() == ""

    provider = FakeProvider(
        [
            fake_assistant_message(
                ToolCall(id="golden-call", name="golden_echo", arguments={"text": "proof"}),
                stop_reason="toolUse",
            ),
            fake_assistant_message("golden-agent-finished"),
        ]
    )
    replies = iter(
        (
            "/golden-status",
            "/model golden/golden-model",
            "/model fake/fake-1",
            "/skill:golden-skill use the golden extension tool",
            "/golden-reload",
            "/golden-status",
            "/golden-new",
            "/golden-status",
            "<switch-original>",
            "/golden-status",
            "/exit",
        )
    )

    async def read_line(_prompt: str) -> str | None:
        reply = next(replies, None)
        if reply == "<switch-original>":
            original = next(session_dir.glob("*.jsonl"))
            return f"/golden-switch {original}"
        return reply

    output = StringIO()
    errors = StringIO()
    exit_code = asyncio.run(
        run_interactive(
            InteractiveOptions(
                cwd=project,
                credential_resolver=DeepSeekCredentialResolver(environ={}, cwd=project),
                model_runtime=ModelRuntime(provider=provider, model=provider.models[0]),
                session_dir=session_dir,
                extension_flags={"golden-mode": True},
            ),
            stdout=output,
            stderr=errors,
            read_line=read_line,
        )
    )

    transcript = output.getvalue()
    assert exit_code == 0
    assert "golden-render:mode:on" in transcript
    assert "model: golden/golden-model" in transcript
    assert "model: fake/fake-1" in transcript
    assert "golden-tool-rendered" in transcript
    assert "golden-agent-finished" in transcript
    assert "golden-reloaded" in transcript
    assert "golden-status mode=True generation=2" in transcript
    assert "golden-new-session" in transcript
    assert "golden-switched" in transcript
    assert errors.getvalue() == ""
    assert provider.call_count == 2
    user_text = "\n".join(
        (
            message.content
            if isinstance(message.content, str)
            else "\n".join(
                block.text for block in message.content if isinstance(block, TextContent)
            )
        )
        for message in provider.calls[0][1].messages
        if isinstance(message, UserMessage)
    )
    assert "golden-package-skill-v1" in user_text
