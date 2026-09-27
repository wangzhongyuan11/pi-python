from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

import pytest

from pi_ai import FakeProvider, fake_assistant_message
from pi_coding_agent.cli.run import HeadlessOptions, run_headless
from pi_coding_agent.deepseek_credentials import DeepSeekCredentialResolver
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.resources.default_loader import DefaultResourceLoader
from pi_coding_agent.sdk import (
    AgentSessionFactory,
    CreateAgentSessionOptions,
    CreatedAgentSession,
    create_agent_session,
)
from pi_coding_agent.tui.runner import InteractiveOptions, run_interactive


@dataclass(frozen=True, slots=True)
class _Snapshot:
    theme: object
    tools: tuple[str, ...]
    resources: tuple[tuple[str, str, str], ...]
    extensions: tuple[str, ...]


def _model_runtime() -> ModelRuntime:
    provider = FakeProvider([fake_assistant_message("ok")])
    return ModelRuntime(provider=provider, model=provider.models[0])


def _snapshot(created: CreatedAgentSession) -> _Snapshot:
    resources = created.services.resources
    assert isinstance(resources, DefaultResourceLoader)
    return _Snapshot(
        theme=created.services.settings.get("theme"),
        tools=tuple(tool.name for tool in created.session.agent.state.tools),
        resources=tuple(
            (item.kind, item.name, item.source) for item in resources.last_result.descriptors
        ),
        extensions=tuple(item.name for item in resources.last_result.extensions),
    )


def test_sdk_headless_and_tui_share_the_complete_trusted_project_bootstrap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = Path(__file__).parents[2] / "fixtures" / "product_project"
    project = tmp_path / "project"
    shutil.copytree(fixture, project)
    monkeypatch.setenv("PI_PYTHON_AGENT_DIR", str(tmp_path / "agent"))
    resolver = DeepSeekCredentialResolver(environ={}, cwd=project)
    snapshots: list[_Snapshot] = []

    async def recording_factory(options: CreateAgentSessionOptions) -> CreatedAgentSession:
        created = await create_agent_session(options)
        snapshots.append(_snapshot(created))
        return created

    factory: AgentSessionFactory = recording_factory

    async def scenario() -> None:
        sdk = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=project,
                model_runtime=_model_runtime(),
                project_trusted=True,
            )
        )
        snapshots.append(_snapshot(sdk))
        await sdk.close()

        assert (
            await run_headless(
                HeadlessOptions(
                    cwd=project,
                    prompt="hello",
                    mode="text",
                    credential_resolver=resolver,
                    model_runtime=_model_runtime(),
                    no_session=True,
                    project_trusted=True,
                    runtime_factory=factory,
                ),
                stdout=StringIO(),
                stderr=StringIO(),
            )
            == 0
        )

        replies = iter(("hello", "/exit"))

        async def read_line(_prompt: str) -> str | None:
            return next(replies, None)

        assert (
            await run_interactive(
                InteractiveOptions(
                    cwd=project,
                    credential_resolver=resolver,
                    model_runtime=_model_runtime(),
                    no_session=True,
                    project_trusted=True,
                    runtime_factory=factory,
                ),
                stdout=StringIO(),
                stderr=StringIO(),
                read_line=read_line,
            )
            == 0
        )

    asyncio.run(scenario())

    assert snapshots == [snapshots[0], snapshots[0], snapshots[0]]
    assert snapshots[0].theme == "fixture-theme"
    assert snapshots[0].tools == ("read", "ls")
    assert ("skill", "fixture-skill", "project") in snapshots[0].resources
    assert snapshots[0].extensions == ("fixture-extension",)
