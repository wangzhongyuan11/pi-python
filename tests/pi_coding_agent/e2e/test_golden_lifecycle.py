"""Golden package complete lifecycle (P16-T03).

One continuous pass over install → restart → Agent tool call → TUI command →
reload/new session → RPC subprocess turn → update → remove, verifying the
installed package stays consistent across every product surface and that
removal takes effect on the next composition.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from io import StringIO
from pathlib import Path

from pi_ai import FakeProvider, TextContent, ToolCall, fake_assistant_message
from pi_coding_agent.cli.main import main
from pi_coding_agent.deepseek_credentials import DeepSeekCredentialResolver
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.rpc.client import RpcClient
from pi_coding_agent.sdk import CreateAgentSessionOptions, create_agent_session
from pi_coding_agent.tui.runner import InteractiveOptions, run_interactive

REPO = Path(__file__).resolve().parents[3]
GOLDEN_PACKAGE = REPO / "tests" / "fixtures" / "golden_package"


def _cli(argv: list[str], project: Path, agent_dir: Path, *, expect: int = 0) -> str:
    stdout = StringIO()
    stderr = StringIO()
    code = main(
        argv,
        stdout=stdout,
        stderr=stderr,
        cwd=project,
        environ={"PI_PYTHON_AGENT_DIR": str(agent_dir)},
    )
    assert code == expect, f"{argv} -> {code}: {stderr.getvalue()}"
    assert "traceback" not in stderr.getvalue().lower()
    return stdout.getvalue()


def _provider(*responses: object) -> ModelRuntime:
    scripted = FakeProvider(list(responses))
    return ModelRuntime(provider=scripted, model=scripted.models[0])


def test_golden_package_survives_the_complete_product_lifecycle(
    tmp_path: Path, monkeypatch: object
) -> None:
    project = tmp_path / "project"
    agent_dir = tmp_path / "agent"
    project.mkdir()
    monkeypatch.setenv("PI_PYTHON_AGENT_DIR", str(agent_dir))  # type: ignore[attr-defined]

    # 1. Install from the local golden package.
    listing = _cli(["install", str(GOLDEN_PACKAGE), "--no-approve"], project, agent_dir)
    assert "Installed" in listing
    assert f"user: {GOLDEN_PACKAGE}" in _cli(["list"], project, agent_dir)

    # 2. Restart (fresh composition) → the Agent calls the extension tool.
    async def agent_stage() -> tuple[tuple[str, ...], str]:
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=project,
                model_runtime=_provider(
                    fake_assistant_message(
                        ToolCall(id="g1", name="golden_echo", arguments={"text": "life"}),
                        stop_reason="toolUse",
                    ),
                    fake_assistant_message("golden agent finished"),
                ),
            )
        )
        try:
            await created.session.prompt("use the golden tool")
            tool_names = tuple(tool.name for tool in created.session.agent.state.tools)
            request_texts = []
            for message in created.session.messages:
                content = getattr(message, "content", None)
                if isinstance(content, str):
                    request_texts.append(content)
                for block in content or ():
                    if isinstance(block, TextContent):
                        request_texts.append(block.text)
            return tool_names, "\n".join(request_texts)
        finally:
            await created.close()

    tool_names, transcript = asyncio.run(agent_stage())
    assert "golden_echo" in tool_names
    # The extension control hook rewrites the golden_echo result content.
    assert "golden-hook-result" in transcript

    # 3. TUI commands and reload/new-session lifecycle.
    replies = iter(("/golden-status", "/golden-reload", "/golden-new", "/exit"))

    async def read_line(_prompt: str) -> str | None:
        return next(replies, None)

    output = StringIO()
    errors = StringIO()
    exit_code = asyncio.run(
        run_interactive(
            InteractiveOptions(
                cwd=project,
                credential_resolver=DeepSeekCredentialResolver(environ={}, cwd=project),
                model_runtime=_provider(fake_assistant_message("idle")),
                project_trusted=True,
            ),
            stdout=output,
            stderr=errors,
            read_line=read_line,
        )
    )
    transcript = output.getvalue()
    assert exit_code == 0, errors.getvalue()
    assert "golden-status mode=False" in transcript
    assert "golden-reloaded" in transcript
    assert "golden-new-session" in transcript

    # 4. RPC subprocess turn through the installed extension tool.
    child = (
        "from pathlib import Path\n"
        "from pi_ai import (\n"
        "    FakeProvider,\n"
        "    ToolCall,\n"
        "    fake_assistant_message,\n"
        "    fake_model,\n"
        ")\n"
        "from pi_coding_agent.model_runtime import ModelRuntime\n"
        "from pi_coding_agent.cli.main import main\n"
        "provider = FakeProvider([\n"
        "    fake_assistant_message(\n"
        "        ToolCall(id='rpc1', name='golden_echo', arguments={'text': 'rpc'}),\n"
        "        stop_reason='toolUse',\n"
        "    ),\n"
        "    fake_assistant_message('rpc golden done'),\n"
        "])\n"
        "raise SystemExit(main(\n"
        "    ['--mode', 'rpc', '--no-builtin-tools'],\n"
        "    model_runtime=ModelRuntime(provider=provider, model=fake_model()),\n"
        "))\n"
    )

    async def rpc_stage() -> str:
        client = await RpcClient.launch(
            (sys.executable, "-u", "-c", child),
            cwd=project,
            env={
                **os.environ,
                "PI_PYTHON_AGENT_DIR": str(agent_dir),
            },
        )
        async with client:
            await client.get_state()
            await client.prompt("rpc golden")
            while (await asyncio.wait_for(client.next_event(), 15))["type"] != "agent_end":
                pass
            messages = await client.request("get_messages")
            assert isinstance(messages, dict)
            return json.dumps(messages["messages"])

    rpc_wire = asyncio.run(rpc_stage())
    assert "golden_echo" in rpc_wire
    assert "golden-hook-result" in rpc_wire

    # 5. Update re-resolves the local package; remove takes effect next run.
    _cli(["update", str(GOLDEN_PACKAGE)], project, agent_dir)
    assert f"user: {GOLDEN_PACKAGE}" in _cli(["list"], project, agent_dir)
    _cli(["remove", str(GOLDEN_PACKAGE)], project, agent_dir)
    assert str(GOLDEN_PACKAGE) not in _cli(["list"], project, agent_dir)

    async def removed_stage() -> tuple[str, ...]:
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=project,
                model_runtime=_provider(fake_assistant_message("bare")),
            )
        )
        try:
            return tuple(tool.name for tool in created.session.agent.state.tools)
        finally:
            await created.close()

    assert "golden_echo" not in asyncio.run(removed_stage())
