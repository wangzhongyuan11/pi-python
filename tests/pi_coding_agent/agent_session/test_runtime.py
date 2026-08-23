from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from pi_coding_agent.agent_session_runtime import (
    AgentSessionRuntime,
    RuntimeComponents,
    RuntimeReason,
    RuntimeTarget,
)
from pi_coding_agent.session.manager import SessionManager


@dataclass(slots=True)
class FakeRuntimeSession:
    name: str
    closed_for: list[RuntimeReason]

    async def close(self, reason: RuntimeReason) -> None:
        self.closed_for.append(reason)


@dataclass(frozen=True, slots=True)
class FakeCwdServices:
    cwd: Path
    generation: int


def _manager(cwd: Path, suffix: str) -> SessionManager:
    return SessionManager.in_memory(
        cwd=cwd,
        session_id=f"session-{suffix}",
        timestamp=f"2026-08-24T00:00:0{suffix}.000Z",
    )


def test_lifecycle_rebuilds_cwd_bound_services_for_every_replacement(tmp_path: Path) -> None:
    async def scenario() -> tuple[
        AgentSessionRuntime[FakeRuntimeSession, FakeCwdServices],
        list[RuntimeTarget],
    ]:
        targets: list[RuntimeTarget] = []

        async def factory(
            target: RuntimeTarget,
        ) -> RuntimeComponents[FakeRuntimeSession, FakeCwdServices]:
            targets.append(target)
            return RuntimeComponents(
                session=FakeRuntimeSession(target.session_manager.header.id, []),
                services=FakeCwdServices(target.cwd, target.generation),
            )

        first_cwd = tmp_path / "first"
        runtime = await AgentSessionRuntime[FakeRuntimeSession, FakeCwdServices].create(
            factory,
            cwd=first_cwd,
            session_manager=_manager(first_cwd, "1"),
        )
        sessions = [runtime.session]

        await runtime.new_session(_manager(first_cwd, "2"))
        sessions.append(runtime.session)
        await runtime.resume(_manager(tmp_path / "resumed", "3"))
        sessions.append(runtime.session)
        await runtime.fork(_manager(tmp_path / "forked", "4"))
        sessions.append(runtime.session)
        await runtime.switch(_manager(tmp_path / "switched", "5"))

        assert [session.closed_for for session in sessions] == [
            ["new"],
            ["resume"],
            ["fork"],
            ["switch"],
        ]
        return runtime, targets

    runtime, targets = asyncio.run(scenario())

    assert [target.reason for target in targets] == [
        "initial",
        "new",
        "resume",
        "fork",
        "switch",
    ]
    assert [target.generation for target in targets] == [0, 1, 2, 3, 4]
    assert runtime.cwd == (tmp_path / "switched").resolve()
    assert runtime.services.cwd == runtime.cwd
    assert runtime.services.generation == 4


def test_resume_cwd_override_controls_rebinding(tmp_path: Path) -> None:
    async def scenario() -> AgentSessionRuntime[FakeRuntimeSession, FakeCwdServices]:
        async def factory(
            target: RuntimeTarget,
        ) -> RuntimeComponents[FakeRuntimeSession, FakeCwdServices]:
            return RuntimeComponents(
                session=FakeRuntimeSession(target.session_manager.header.id, []),
                services=FakeCwdServices(target.cwd, target.generation),
            )

        original = tmp_path / "original"
        runtime = await AgentSessionRuntime[FakeRuntimeSession, FakeCwdServices].create(
            factory,
            cwd=original,
            session_manager=_manager(original, "1"),
        )
        override = tmp_path / "override"
        await runtime.resume(_manager(tmp_path / "stored", "2"), cwd_override=override)
        return runtime

    runtime = asyncio.run(scenario())

    assert runtime.cwd == (tmp_path / "override").resolve()
    assert runtime.services.cwd == runtime.cwd


def test_dispose_closes_current_session_once(tmp_path: Path) -> None:
    async def scenario() -> FakeRuntimeSession:
        async def factory(
            target: RuntimeTarget,
        ) -> RuntimeComponents[FakeRuntimeSession, FakeCwdServices]:
            return RuntimeComponents(
                session=FakeRuntimeSession(target.session_manager.header.id, []),
                services=FakeCwdServices(target.cwd, target.generation),
            )

        runtime = await AgentSessionRuntime[FakeRuntimeSession, FakeCwdServices].create(
            factory,
            cwd=tmp_path,
            session_manager=_manager(tmp_path, "1"),
        )
        session = runtime.session
        await runtime.close()
        await runtime.close()
        return session

    assert asyncio.run(scenario()).closed_for == ["quit"]
