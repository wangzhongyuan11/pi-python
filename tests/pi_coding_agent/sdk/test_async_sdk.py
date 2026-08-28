from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import BaseModel

from pi_agent import AgentTool, AgentToolResult
from pi_ai import FakeProvider, Model, TextContent, fake_assistant_message, fake_model
from pi_coding_agent.branch_summary import BranchSummarizer
from pi_coding_agent.builtin_extensions.permission_gate import (
    PermissionDeniedError,
    PermissionGate,
)
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.ports import NoopExtensionRuntime, ResourceDescriptor
from pi_coding_agent.resources.default_loader import DefaultResourceLoader
from pi_coding_agent.resources.trust import TrustDecision
from pi_coding_agent.sdk import CreateAgentSessionOptions, create_agent_session
from pi_coding_agent.services import ServiceOverrides
from pi_coding_agent.session.manager import SessionManager
from pi_coding_agent.session.models import (
    BranchSummaryEntry,
    ModelChangeEntry,
    SessionEntry,
    SessionInfoEntry,
    ThinkingLevelChangeEntry,
)


def _manager(cwd: Path) -> SessionManager:
    return SessionManager.in_memory(
        cwd=cwd,
        session_id="sdk-session",
        timestamp="2026-08-24T00:00:00.000Z",
    )


def test_async_factory_composes_prompt_path_and_context_manager_cleanup(tmp_path: Path) -> None:
    async def scenario() -> tuple[bool, int, tuple[str, ...]]:
        provider = FakeProvider([fake_assistant_message("sdk answer")])
        runtime = ModelRuntime(provider=provider, model=provider.models[0])
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=runtime,
                session_manager=_manager(tmp_path),
                agent_clock=lambda: 1,
                entry_id_factory=iter(("user", "assistant")).__next__,
                timestamp_factory=lambda: "2026-08-24T00:00:01.000Z",
            )
        )
        owned_session = created.session

        async with created as active:
            assert active is created
            await active.session.prompt("hello from sdk")

        return (
            owned_session.is_closed,
            provider.call_count,
            tuple(message.role for message in owned_session.messages),
        )

    closed, call_count, roles = asyncio.run(scenario())

    assert closed
    assert call_count == 1
    assert roles == ("user", "assistant")


def test_async_factory_composes_trusted_project_system_and_context_files(
    tmp_path: Path,
) -> None:
    class TrustedProject:
        def get(self, cwd: Path) -> TrustDecision:
            assert cwd == project
            return TrustDecision.TRUSTED

    project = tmp_path / "project"
    agent_dir = tmp_path / "agent"
    (project / ".pi-python").mkdir(parents=True)
    (project / ".pi-python" / "SYSTEM.md").write_text("trusted project system", encoding="utf-8")
    (project / ".pi-python" / "skills").mkdir()
    (project / ".pi-python" / "skills" / "architecture.md").write_text(
        "---\nname: architecture\ndescription: Inspect project structure\n---\nDetails",
        encoding="utf-8",
    )
    (project / "AGENTS.md").write_text("trusted project rules", encoding="utf-8")
    provider = FakeProvider([fake_assistant_message("done")])

    async def scenario() -> str:
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=project,
                model_runtime=ModelRuntime(provider=provider, model=provider.models[0]),
                session_manager=_manager(project),
                service_overrides=ServiceOverrides(
                    resources=DefaultResourceLoader(
                        trust_store=TrustedProject(),
                        agent_dir=agent_dir,
                    ),
                    extensions=NoopExtensionRuntime(),
                ),
            )
        )
        async with created:
            await created.session.prompt("inspect")
        prompt = provider.calls[0][1].system_prompt
        assert prompt is not None
        return prompt

    prompt = asyncio.run(scenario())

    assert prompt.startswith("trusted project system")
    assert "trusted project rules" in prompt
    assert "<name>architecture</name>" in prompt
    assert project.resolve().as_posix() in prompt


def test_async_context_cleanup_runs_when_caller_raises(tmp_path: Path) -> None:
    async def scenario() -> bool:
        provider = FakeProvider()
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=ModelRuntime(provider=provider, model=provider.models[0]),
                session_manager=_manager(tmp_path),
            )
        )
        owned_session = created.session
        with pytest.raises(RuntimeError, match="caller failed"):
            async with created:
                raise RuntimeError("caller failed")
        return owned_session.is_closed

    assert asyncio.run(scenario())


def test_sdk_starts_resources_and_extensions_and_closes_extensions(tmp_path: Path) -> None:
    class Resources:
        def __init__(self) -> None:
            self.calls: list[Path] = []

        def discover(self, cwd: Path) -> tuple[ResourceDescriptor, ...]:
            self.calls.append(cwd)
            return ()

    class Extensions:
        def __init__(self) -> None:
            self.started = 0
            self.closed = 0

        @property
        def tools(self):
            return ()

        @property
        def providers(self):
            return ()

        async def start(self) -> tuple[ResourceDescriptor, ...]:
            self.started += 1
            return ()

        async def close(self) -> None:
            self.closed += 1

    async def scenario() -> tuple[Resources, Extensions]:
        resources = Resources()
        extensions = Extensions()
        provider = FakeProvider()
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=ModelRuntime(provider=provider, model=provider.models[0]),
                session_manager=_manager(tmp_path),
                service_overrides=ServiceOverrides(
                    resources=resources,
                    extensions=extensions,
                ),
            )
        )
        await created.close()
        return resources, extensions

    resources, extensions = asyncio.run(scenario())
    assert resources.calls == [tmp_path.resolve()]
    assert extensions.started == 1
    assert extensions.closed == 1


def test_sdk_adds_extension_tools_before_applying_permission_gate(tmp_path: Path) -> None:
    class Input(BaseModel):
        value: str

    async def execute(*_args: object) -> AgentToolResult[None]:
        return AgentToolResult(content=(TextContent(text="ran"),), details=None)

    tool = AgentTool(
        name="extension-tool",
        label="extension-tool",
        description="extension tool",
        parameter_type=Input,
        execute=execute,
    )

    class Resources:
        def discover(self, cwd: Path) -> tuple[ResourceDescriptor, ...]:
            del cwd
            return ()

    class Extensions:
        @property
        def tools(self):
            return (tool,)

        @property
        def providers(self):
            return ()

        async def start(self) -> tuple[ResourceDescriptor, ...]:
            return ()

        async def close(self) -> None:
            return None

    async def scenario() -> None:
        provider = FakeProvider()
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=ModelRuntime(provider=provider, model=provider.models[0]),
                session_manager=_manager(tmp_path),
                tools=(),
                permission_gate=PermissionGate(enabled=True, confirmer=lambda _name: False),
                service_overrides=ServiceOverrides(
                    resources=Resources(),
                    extensions=Extensions(),
                ),
            )
        )
        wrapped = created.session.state.tools[0]
        with pytest.raises(PermissionDeniedError):
            await wrapped.execute("call", Input(value="x"))
        await created.close()

    asyncio.run(scenario())


def test_sdk_registers_extension_provider_before_restoring_session_model(tmp_path: Path) -> None:
    class OtherProvider(FakeProvider):
        @property
        def id(self) -> str:
            return "other"

        @property
        def models(self) -> tuple[Model, ...]:
            return (replace(fake_model(), provider="other", id="other-model"),)

    class Resources:
        def discover(self, cwd: Path) -> tuple[ResourceDescriptor, ...]:
            del cwd
            return ()

    class Extensions:
        def __init__(self, provider: OtherProvider) -> None:
            self._provider = provider

        @property
        def tools(self):
            return ()

        @property
        def providers(self):
            return (self._provider,)

        async def start(self) -> tuple[ResourceDescriptor, ...]:
            return ()

        async def close(self) -> None:
            return None

    async def scenario() -> tuple[str, str]:
        manager = _manager(tmp_path)
        manager.append(
            SessionInfoEntry(
                type="session_info",
                id="root",
                parent_id=None,
                timestamp="2026-08-24T00:00:01Z",
            )
        )
        manager.append(
            ModelChangeEntry(
                type="model_change",
                id="model",
                parent_id="root",
                timestamp="2026-08-24T00:00:02Z",
                provider="other",
                model_id="other-model",
            )
        )
        primary = FakeProvider()
        other = OtherProvider()
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=ModelRuntime(provider=primary, model=primary.models[0]),
                session_manager=manager,
                service_overrides=ServiceOverrides(
                    resources=Resources(),
                    extensions=Extensions(other),
                ),
            )
        )
        state = created.session.state
        await created.close()
        return state.model.provider, state.model.id

    assert asyncio.run(scenario()) == ("other", "other-model")


def test_factory_rejects_session_cwd_mismatch(tmp_path: Path) -> None:
    async def scenario() -> None:
        provider = FakeProvider()
        with pytest.raises(ValueError, match="session cwd"):
            await create_agent_session(
                CreateAgentSessionOptions(
                    cwd=tmp_path / "requested",
                    model_runtime=ModelRuntime(provider=provider, model=provider.models[0]),
                    session_manager=_manager(tmp_path / "stored"),
                )
            )

    asyncio.run(scenario())


class FakeBranchSummarizer(BranchSummarizer):
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    async def summarize(self, entries: tuple[SessionEntry, ...]) -> str:
        self.calls.append(tuple(entry.id for entry in entries))
        return "abandoned work"


def test_sdk_branch_navigation_can_persist_divergent_summary(tmp_path: Path) -> None:
    async def scenario() -> tuple[FakeBranchSummarizer, SessionManager, tuple[str, ...]]:
        manager = _manager(tmp_path)
        manager.append(
            SessionInfoEntry(
                type="session_info", id="root", parent_id=None, timestamp="2026-08-24T00:00:01Z"
            )
        )
        manager.append(
            SessionInfoEntry(
                type="session_info", id="target", parent_id="root", timestamp="2026-08-24T00:00:02Z"
            )
        )
        manager.branch("root")
        manager.append(
            SessionInfoEntry(
                type="session_info",
                id="abandoned",
                parent_id="root",
                timestamp="2026-08-24T00:00:03Z",
            )
        )
        provider = FakeProvider()
        summarizer = FakeBranchSummarizer()
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=ModelRuntime(provider=provider, model=provider.models[0]),
                session_manager=manager,
                branch_summarizer=summarizer,
                entry_id_factory=lambda: "summary",
                timestamp_factory=lambda: "2026-08-24T00:00:04Z",
            )
        )
        entry = await created.session.branch("target", summarize=True)
        roles = tuple(message.role for message in created.session.messages)
        await created.close()
        assert isinstance(entry, BranchSummaryEntry)
        return summarizer, manager, roles

    summarizer, manager, roles = asyncio.run(scenario())

    assert summarizer.calls == [("abandoned",)]
    assert manager.leaf_id == "summary"
    assert roles == ("branchSummary",)


class MultiModelFakeProvider(FakeProvider):
    def __init__(self) -> None:
        super().__init__()
        self._available_models = (
            fake_model(),
            replace(fake_model(), id="fake-2", name="Second Fake Model"),
        )

    @property
    def models(self) -> tuple[Model, ...]:
        return self._available_models


def test_sdk_resume_restores_recorded_model_and_thinking_level(tmp_path: Path) -> None:
    async def scenario() -> tuple[str, str]:
        manager = _manager(tmp_path)
        manager.append(
            SessionInfoEntry(
                type="session_info", id="root", parent_id=None, timestamp="2026-08-24T00:00:01Z"
            )
        )
        manager.append(
            ModelChangeEntry(
                type="model_change",
                id="model",
                parent_id="root",
                timestamp="2026-08-24T00:00:02Z",
                provider="fake",
                model_id="fake-2",
            )
        )
        manager.append(
            ThinkingLevelChangeEntry(
                type="thinking_level_change",
                id="thinking",
                parent_id="model",
                timestamp="2026-08-24T00:00:03Z",
                thinking_level="low",
            )
        )
        provider = MultiModelFakeProvider()
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=ModelRuntime(provider=provider, model=provider.models[0]),
                session_manager=manager,
                thinking_level="high",
            )
        )
        state = created.session.state
        await created.close()
        return state.model.id, state.thinking_level

    assert asyncio.run(scenario()) == ("fake-2", "low")
