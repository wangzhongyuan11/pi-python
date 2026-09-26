"""Historical defect regression: extension subprocesses must not outlive the runtime."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from pi_ai import FakeProvider, fake_model
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.sdk import CreateAgentSessionOptions, create_agent_session
from pi_coding_agent.session.manager import SessionManager


def test_extension_exec_processes_terminate_on_session_close(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager = SessionManager.create(
            cwd=tmp_path,
            session_dir=tmp_path,
            session_id="regression00000000000000000000000ee",
            timestamp="2026-09-01T00:00:00.000Z",
        )
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=ModelRuntime(provider=FakeProvider([]), model=fake_model()),
                session_manager=manager,
            )
        )
        try:
            actions = created.session.services.extensions.actions
            long_running = asyncio.create_task(
                actions.exec(sys.executable, ("-c", "import time; time.sleep(30)"))
            )
            await asyncio.sleep(0.2)  # let the child process spawn
            await created.close()
            # The child must die with the runtime instead of sleeping for 30s.
            result = await asyncio.wait_for(long_running, timeout=10)
            assert result.code != 0
        finally:
            await created.close()

    asyncio.run(scenario())
