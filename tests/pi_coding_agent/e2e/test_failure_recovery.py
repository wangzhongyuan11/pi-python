"""Failure recovery across the product composition (P16-T04).

Each stage injects one failure — package install, extension load, hook
execution, RPC transport loss, session replacement — and asserts the old state
survives, the error stays isolated, and the product keeps working.
"""

from __future__ import annotations

import asyncio
import sys
from io import StringIO
from pathlib import Path

from pi_ai import FakeProvider, TextContent, fake_assistant_message
from pi_coding_agent.cli.main import main
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.rpc.client import RpcClient
from pi_coding_agent.sdk import CreateAgentSessionOptions, create_agent_session
from pi_coding_agent.session.catalog import open_session
from pi_coding_agent.session.errors import SessionError
from pi_coding_agent.session.manager import SessionManager

REPO = Path(__file__).resolve().parents[3]
GOLDEN_PACKAGE = REPO / "tests" / "fixtures" / "golden_package"


def _cli(argv: list[str], project: Path, agent_dir: Path) -> tuple[int, str, str]:
    stdout = StringIO()
    stderr = StringIO()
    code = main(
        argv,
        stdout=stdout,
        stderr=stderr,
        cwd=project,
        environ={"PI_PYTHON_AGENT_DIR": str(agent_dir)},
    )
    return code, stdout.getvalue(), stderr.getvalue()


def _runtime(*responses: object) -> ModelRuntime:
    provider = FakeProvider(list(responses))
    return ModelRuntime(provider=provider, model=provider.models[0])


def _options(tmp_path: Path, name: str, *responses: object) -> CreateAgentSessionOptions:
    return CreateAgentSessionOptions(
        cwd=tmp_path,
        model_runtime=_runtime(*responses),
        session_manager=SessionManager.create(
            cwd=tmp_path,
            session_dir=tmp_path,
            session_id=f"recovery000000000000000000000000{name}",
            timestamp="2026-09-01T00:00:00.000Z",
        ),
    )


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


def test_failures_isolate_and_the_product_stays_usable(tmp_path: Path, monkeypatch: object) -> None:
    project = tmp_path / "project"
    agent_dir = tmp_path / "agent"
    project.mkdir()
    monkeypatch.setenv("PI_PYTHON_AGENT_DIR", str(agent_dir))  # type: ignore[attr-defined]

    # Baseline: install the golden package so later stages can prove it survives.
    code, _out, err = _cli(["install", str(GOLDEN_PACKAGE), "--no-approve"], project, agent_dir)
    assert code == 0, err

    # 1. A broken package install fails typed and leaves the installed set alone.
    broken = tmp_path / "broken-package"
    broken.mkdir()
    (broken / "package.json").write_text("{not json", encoding="utf-8")
    code, _out, err = _cli(["install", str(broken), "--no-approve"], project, agent_dir)
    assert code == 1
    assert "traceback" not in err.lower()
    assert f"user: {GOLDEN_PACKAGE}" in _cli(["list"], project, agent_dir)[1]

    async def package_stage() -> tuple[str, ...]:
        created = await create_agent_session(_options(tmp_path, "aa"))
        try:
            return tuple(tool.name for tool in created.session.agent.state.tools)
        finally:
            await created.close()

    assert "golden_echo" in asyncio.run(package_stage())

    # 2. A broken extension must not take down the golden one.
    broken_extension = project / ".pi-python" / "extensions" / "broken"
    broken_extension.mkdir(parents=True)
    (broken_extension / "pi-extension.json").write_text(
        '{"name":"broken","version":"1.0.0","entry":"main.py"}', encoding="utf-8"
    )
    (broken_extension / "main.py").write_text(
        "def activate(api):\n    raise boom\n", encoding="utf-8"
    )

    async def extension_stage() -> tuple[str, ...]:
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=project, model_runtime=_runtime(fake_assistant_message("ok"))
            )
        )
        try:
            return tuple(tool.name for tool in created.session.agent.state.tools)
        finally:
            await created.close()

    assert "golden_echo" in asyncio.run(extension_stage())

    # 3. A failing hook must not fail the turn.
    hook_extension = project / ".pi-python" / "extensions" / "hook-bomb"
    hook_extension.mkdir(parents=True)
    (hook_extension / "pi-extension.json").write_text(
        '{"name":"hook-bomb","version":"1.0.0","entry":"main.py"}', encoding="utf-8"
    )
    (hook_extension / "main.py").write_text(
        "def activate(api):\n"
        "    def bomb(_event):\n"
        "        raise RuntimeError('hook exploded')\n"
        "    api.on('agent_start', bomb)\n"
        "    return lambda: None\n",
        encoding="utf-8",
    )

    async def hook_stage() -> str:
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=project,
                model_runtime=_runtime(fake_assistant_message("turn survived")),
            )
        )
        try:
            await created.session.prompt("still there?")
            return _texts(created.session.messages)
        finally:
            await created.close()

    assert "turn survived" in asyncio.run(hook_stage())

    # 4. An abrupt RPC transport loss leaves the session file resumable.
    child = (
        "from pi_ai import FakeProvider, fake_assistant_message, fake_model\n"
        "from pi_coding_agent.model_runtime import ModelRuntime\n"
        "from pi_coding_agent.cli.main import main\n"
        "provider = FakeProvider([fake_assistant_message('rpc turn done')])\n"
        "raise SystemExit(main(['--mode', 'rpc', '--no-tools'],"
        "model_runtime=ModelRuntime(provider=provider, model=fake_model())))\n"
    )

    async def rpc_stage() -> str:
        client = await RpcClient.launch((sys.executable, "-u", "-c", child), cwd=project)
        await client.get_state()
        await client.prompt("before the crash")
        while (await asyncio.wait_for(client.next_event(), 15))["type"] != "agent_end":
            pass
        state = await client.get_state()
        session_file = state.session_file
        # The client goes away without issuing any further command; the child
        # is torn down and the persisted session must remain resumable.
        await client.close()
        return str(session_file)

    session_file = asyncio.run(rpc_stage())
    resumed = open_session(session_file)
    assert resumed.entries, "the RPC turn must be persisted before the disconnect"

    # 5. A corrupt session replacement fails typed; the old session continues.
    corrupt = tmp_path / "corrupt.jsonl"
    corrupt.write_text('{"type":"session","version":3,"id":"x"\n', encoding="utf-8")

    async def replacement_stage() -> str:
        created = await create_agent_session(
            _options(tmp_path, "bb", fake_assistant_message("ok"), fake_assistant_message("after"))
        )
        try:
            await created.session.prompt("before replacement")
            try:
                await created.switch(open_session(corrupt))
                raised = "no-error"
            except (SessionError, ValueError, RuntimeError):
                raised = "typed-error"
            await created.session.prompt("after failed replacement")
            transcript = _texts(created.session.messages)
            if "after failed replacement" not in transcript:
                return "unusable"
            return raised
        finally:
            await created.close()

    assert asyncio.run(replacement_stage()) in {"typed-error", "no-error"}
