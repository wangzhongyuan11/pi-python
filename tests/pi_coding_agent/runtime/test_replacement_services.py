from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from pi_ai import FakeProvider
from pi_coding_agent.agent_session import AgentSession
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.sdk import CreateAgentSessionOptions, create_agent_session
from pi_coding_agent.services import ProductServices
from pi_coding_agent.session.manager import SessionManager


def _manager(cwd: Path, name: str) -> SessionManager:
    return SessionManager.in_memory(
        cwd=cwd,
        session_id=f"session-{name}",
        timestamp="2026-08-31T00:00:00.000Z",
    )


def test_every_session_replacement_rebuilds_all_cwd_bound_product_services(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PI_PYTHON_AGENT_DIR", str(tmp_path / "agent"))

    async def scenario() -> list[tuple[AgentSession, ProductServices, tuple[int, ...]]]:
        first = tmp_path / "first"
        provider = FakeProvider()
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=first,
                session_manager=_manager(first, "initial"),
                model_runtime=ModelRuntime(provider=provider, model=provider.models[0]),
            )
        )
        snapshots: list[tuple[AgentSession, ProductServices, tuple[int, ...]]] = []

        def record() -> None:
            snapshots.append(
                (
                    created.session,
                    created.services,
                    tuple(id(tool) for tool in created.session.agent.state.tools),
                )
            )

        record()
        await created.new_session(_manager(first, "new"))
        record()
        await created.resume(_manager(tmp_path / "resumed", "resume"))
        record()
        await created.fork(_manager(tmp_path / "forked", "fork"))
        record()
        await created.switch(_manager(tmp_path / "switched", "switch"))
        record()
        await created.close()
        return snapshots

    snapshots = asyncio.run(scenario())

    sessions = [item[0] for item in snapshots]
    services = [item[1] for item in snapshots]
    tool_ids = [item[2] for item in snapshots]
    expected_cwds = [
        tmp_path / "first",
        tmp_path / "first",
        tmp_path / "resumed",
        tmp_path / "forked",
        tmp_path / "switched",
    ]
    assert all(session.is_closed for session in sessions)
    assert [service.cwd for service in services] == [path.resolve() for path in expected_cwds]
    assert len({id(service) for service in services}) == len(services)
    assert len({id(service.settings) for service in services}) == len(services)
    assert len({id(service.resources) for service in services}) == len(services)
    assert len({id(service.extensions) for service in services}) == len(services)
    assert len(set(tool_ids)) == len(tool_ids)
