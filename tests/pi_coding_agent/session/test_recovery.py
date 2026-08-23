from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path

from pi_ai import TextContent, ToolCall, ToolResultMessage, fake_assistant_message
from pi_ai.wire.messages import dump_message
from pi_coding_agent.agent_session_runtime import (
    AgentSessionRuntime,
    RuntimeComponents,
    RuntimeReason,
    RuntimeTarget,
)
from pi_coding_agent.session.agent_messages import parse_message_entry
from pi_coding_agent.session.manager import SessionManager
from pi_coding_agent.session.models import MessageEntry
from pi_coding_agent.session.recovery import RECOVERY_MESSAGE, recover_unmatched_tool_calls


class RuntimeSession:
    async def close(self, reason: RuntimeReason) -> None:
        del reason


def _manager(cwd: Path, session_id: str) -> SessionManager:
    return SessionManager.in_memory(
        cwd=cwd,
        session_id=session_id,
        timestamp="2026-08-24T00:00:00.000Z",
    )


def _seed_calls(manager: SessionManager) -> None:
    manager.append(
        MessageEntry(
            type="message",
            id="calls",
            parent_id=None,
            timestamp="2026-08-24T00:00:01.000Z",
            message=dump_message(
                fake_assistant_message(
                    (
                        ToolCall(id="call-1", name="write", arguments={"path": "a"}),
                        ToolCall(id="call-2", name="read", arguments={"path": "b"}),
                    ),
                    stop_reason="toolUse",
                    timestamp=1,
                )
            ),
        )
    )
    manager.append(
        MessageEntry(
            type="message",
            id="result-2",
            parent_id="calls",
            timestamp="2026-08-24T00:00:02.000Z",
            message=dump_message(
                ToolResultMessage(
                    tool_call_id="call-2",
                    tool_name="read",
                    content=(TextContent(text="done"),),
                    is_error=False,
                    timestamp=2,
                )
            ),
        )
    )


def test_recovery_appends_each_unmatched_call_once_in_model_order(tmp_path: Path) -> None:
    manager = _manager(tmp_path, "recover-direct")
    _seed_calls(manager)
    ids: Iterator[str] = iter(("recovered-1", "unexpected"))

    first = recover_unmatched_tool_calls(
        manager,
        entry_id_factory=ids.__next__,
        timestamp_factory=lambda: "2026-08-24T00:00:03.000Z",
    )
    second = recover_unmatched_tool_calls(manager)

    assert [entry.id for entry in first] == ["recovered-1"]
    assert second == ()
    recovered = parse_message_entry(first[0])
    assert isinstance(recovered, ToolResultMessage)
    assert recovered.tool_call_id == "call-1"
    assert recovered.tool_name == "write"
    assert recovered.is_error
    assert recovered.content == (TextContent(text=RECOVERY_MESSAGE),)


def test_runtime_recovers_before_binding_without_tool_execution(tmp_path: Path) -> None:
    async def scenario() -> tuple[int, ToolResultMessage]:
        manager = _manager(tmp_path, "recover-runtime")
        _seed_calls(manager)
        factory_calls = 0

        async def factory(
            target: RuntimeTarget,
        ) -> RuntimeComponents[RuntimeSession, None]:
            nonlocal factory_calls
            factory_calls += 1
            latest = target.session_manager.entries[-1]
            assert isinstance(latest, MessageEntry)
            recovered = parse_message_entry(latest)
            assert isinstance(recovered, ToolResultMessage)
            return RuntimeComponents(session=RuntimeSession(), services=None)

        runtime = await AgentSessionRuntime[RuntimeSession, None].create(
            factory,
            cwd=tmp_path,
            session_manager=manager,
        )
        latest = manager.entries[-1]
        assert isinstance(latest, MessageEntry)
        recovered = parse_message_entry(latest)
        assert isinstance(recovered, ToolResultMessage)
        await runtime.close()
        return factory_calls, recovered

    factory_calls, recovered = asyncio.run(scenario())

    assert factory_calls == 1
    assert recovered.tool_call_id == "call-1"
    assert recovered.is_error
