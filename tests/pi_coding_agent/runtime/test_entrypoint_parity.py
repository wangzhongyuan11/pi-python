from __future__ import annotations

import asyncio
from io import StringIO
from pathlib import Path
from typing import NoReturn, TextIO

import pytest

from pi_ai import FakeProvider
from pi_coding_agent.cli.main import main
from pi_coding_agent.cli.run import HeadlessOptions, run_headless
from pi_coding_agent.deepseek_credentials import DeepSeekCredentialResolver
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.ports import NoopExtensionRuntime, NoopResourceLoader
from pi_coding_agent.sdk import AgentSessionFactory, CreateAgentSessionOptions
from pi_coding_agent.services import ServiceOverrides
from pi_coding_agent.tui.runner import InteractiveOptions, run_interactive


class _Captured(RuntimeError):
    pass


def _runtime() -> ModelRuntime:
    provider = FakeProvider()
    return ModelRuntime(provider=provider, model=provider.models[0])


def test_headless_and_tui_send_the_same_input_to_the_sdk_factory(tmp_path: Path) -> None:
    captured: list[CreateAgentSessionOptions] = []
    overrides = ServiceOverrides(
        resources=NoopResourceLoader(),
        extensions=NoopExtensionRuntime(),
    )

    async def capture(options: CreateAgentSessionOptions) -> NoReturn:
        captured.append(options)
        raise _Captured

    factory: AgentSessionFactory = capture
    resolver = DeepSeekCredentialResolver(environ={}, cwd=tmp_path)
    common = {
        "cwd": tmp_path,
        "credential_resolver": resolver,
        "model_runtime": _runtime(),
        "no_session": True,
        "service_overrides": overrides,
        "runtime_factory": factory,
    }

    with pytest.raises(_Captured):
        asyncio.run(
            run_headless(
                HeadlessOptions(prompt="test", mode="text", **common),
                stdout=StringIO(),
                stderr=StringIO(),
            )
        )
    with pytest.raises(_Captured):
        asyncio.run(
            run_interactive(
                InteractiveOptions(**common),
                stdout=StringIO(),
                stderr=StringIO(),
            )
        )

    assert len(captured) == 2
    assert all(item.cwd == tmp_path for item in captured)
    assert all(item.service_overrides is overrides for item in captured)
    assert all(item.no_tools is None for item in captured)
    assert all(item.tool_names is None for item in captured)
    assert all(item.exclude_tools is None for item in captured)


def test_cli_forwards_the_same_factory_and_service_graph_to_both_modes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pi_coding_agent.cli.main as cli_main

    calls: list[HeadlessOptions | InteractiveOptions] = []
    overrides = ServiceOverrides(
        resources=NoopResourceLoader(),
        extensions=NoopExtensionRuntime(),
    )

    async def factory(_options: CreateAgentSessionOptions) -> NoReturn:
        raise AssertionError("adapter stub must intercept before factory execution")

    async def headless(options: HeadlessOptions, *, stdout: TextIO, stderr: TextIO) -> int:
        del stdout, stderr
        calls.append(options)
        return 0

    async def interactive(options: InteractiveOptions, *, stdout: TextIO, stderr: TextIO) -> int:
        del stdout, stderr
        calls.append(options)
        return 0

    monkeypatch.setattr(cli_main, "run_headless", headless)
    monkeypatch.setattr(cli_main, "run_interactive", interactive)

    assert (
        main(
            ["--approve", "--print", "hello"],
            cwd=tmp_path,
            stdout=StringIO(),
            stderr=StringIO(),
            environ={},
            model_runtime=_runtime(),
            service_overrides=overrides,
            runtime_factory=factory,
        )
        == 0
    )
    assert (
        main(
            ["--approve"],
            cwd=tmp_path,
            stdout=StringIO(),
            stderr=StringIO(),
            environ={},
            model_runtime=_runtime(),
            service_overrides=overrides,
            runtime_factory=factory,
        )
        == 0
    )

    assert len(calls) == 2
    assert all(item.service_overrides is overrides for item in calls)
    assert all(item.runtime_factory is factory for item in calls)
    assert all(item.project_trusted for item in calls)
