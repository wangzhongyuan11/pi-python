"""Bash session environment (PI_*) and command prefix wiring (P11.5-T13)."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

import pytest

from pi_coding_agent.tools.bash import execute_bash
from pi_coding_agent.tools.bash_resolver import BashConfig
from pi_coding_agent.tools.operations import OutputSink
from pi_coding_agent.tools.registry import create_all_tools


class _CapturingProcessOperations:
    def __init__(self) -> None:
        self.argv: tuple[str, ...] | None = None
        self.stdin: bytes | None = None
        self.environment: dict[str, str] | None = None

    async def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        environment: Mapping[str, str] | None,
        stdin: bytes | None,
        stdout: OutputSink,
        stderr: OutputSink,
        timeout: float | None,
        abort_event: asyncio.Event | None,
    ) -> int:
        del cwd, timeout, abort_event, stdout, stderr
        self.argv = tuple(argv)
        self.stdin = stdin
        self.environment = dict(environment) if environment is not None else None
        return 0


def _config() -> BashConfig:
    return BashConfig(executable="bash", arguments=("-c",), command_transport="argv")


def test_execute_bash_merges_session_environment() -> None:
    operations = _CapturingProcessOperations()
    asyncio.run(
        execute_bash(
            "echo hi",
            cwd=Path.cwd(),
            config=_config(),
            operations=operations,
            environment={"PATH": "/usr/bin"},
            session_environment={"PI_SESSION_ID": "s-1", "PI_MODEL": "m-1"},
        )
    )
    assert operations.environment is not None
    assert operations.environment["PATH"] == "/usr/bin"
    assert operations.environment["PI_SESSION_ID"] == "s-1"
    assert operations.environment["PI_MODEL"] == "m-1"


def test_execute_bash_prepends_command_prefix() -> None:
    operations = _CapturingProcessOperations()
    asyncio.run(
        execute_bash(
            "echo hi",
            cwd=Path.cwd(),
            config=_config(),
            operations=operations,
            command_prefix="cd /work",
        )
    )
    assert operations.argv is not None
    assert operations.argv[-1] == "cd /work\necho hi"


def test_registry_bash_tool_receives_session_environment_and_prefix(
    tmp_path: Path,
) -> None:
    operations = _CapturingProcessOperations()

    def provider() -> dict[str, str]:
        return {"PI_PROVIDER": "deepseek", "PI_MODEL": "deepseek-v4-pro"}

    (bash_tool,) = create_all_tools(
        cwd=tmp_path,
        tool_names=("bash",),
        process_operations=operations,
        bash_config=_config(),
        session_environment_provider=provider,
        command_prefix="set -e",
    )
    params = bash_tool.validate_arguments({"command": "git status"})
    asyncio.run(bash_tool.execute("call-bash", params))
    assert operations.environment is not None
    assert operations.environment.get("PI_PROVIDER") == "deepseek"
    assert operations.argv is not None
    assert operations.argv[-1] == "set -e\ngit status"


def test_sdk_factory_supplies_session_environment_and_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pi_coding_agent.sdk as sdk
    from pi_ai import FakeProvider, fake_assistant_message
    from pi_coding_agent.model_runtime import ModelRuntime
    from pi_coding_agent.ports import InMemorySettings
    from pi_coding_agent.sdk import CreateAgentSessionOptions, create_agent_session
    from pi_coding_agent.services import ServiceOverrides
    from pi_coding_agent.session.manager import SessionManager

    captured: dict[str, object] = {}

    def create_tools(**kwargs: object):
        captured.update(kwargs)
        return ()

    monkeypatch.setattr(sdk, "create_all_tools", create_tools)

    async def scenario() -> None:
        provider = FakeProvider([fake_assistant_message("ok")])
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=ModelRuntime(provider=provider, model=provider.models[0]),
                session_manager=SessionManager.in_memory(
                    cwd=tmp_path,
                    session_id="bash-env",
                    timestamp="2026-08-30T00:00:00.000Z",
                ),
                service_overrides=ServiceOverrides(
                    settings=InMemorySettings({"shellCommandPrefix": "set -e"})
                ),
                agent_clock=lambda: 1,
            )
        )
        await created.close()

    asyncio.run(scenario())

    assert captured.get("command_prefix") == "set -e"
    environment_provider = captured.get("session_environment_provider")
    assert callable(environment_provider)
    environment = cast("dict[str, str]", environment_provider())
    assert environment["PI_SESSION_ID"] == "bash-env"
    assert environment["PI_PROVIDER"] == "fake"
    assert environment["PI_MODEL"] == "fake-1"
