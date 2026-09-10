from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from pi_ai import FakeProvider, Model, fake_assistant_message, fake_model
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.ports import ResourceRoot
from pi_coding_agent.rpc.commands import RpcCommandAdapter
from pi_coding_agent.rpc.models import parse_rpc_command
from pi_coding_agent.rpc.server import RpcOutput, RpcServer
from pi_coding_agent.sdk import CreateAgentSessionOptions, create_agent_session
from pi_coding_agent.services import ServiceOverrides
from pi_coding_agent.session.manager import SessionManager
from pi_coding_agent.tools.bash import BashResult


class _Models(FakeProvider):
    @property
    def models(self) -> tuple[Model, ...]:
        return (fake_model(), replace(fake_model(), id="fake-2", name="Fake 2"))


def test_server_serializes_void_commands_and_continues_after_lookup_error(tmp_path: Path) -> None:
    async def scenario() -> list[dict[str, object]]:
        provider = _Models()
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=ModelRuntime(provider=provider, model=provider.models[0]),
            )
        )
        async with created:
            lines: list[str] = []
            output = RpcOutput(lines.append)
            await output.start()
            server = RpcServer(
                session=created.session, output=output, commands=RpcCommandAdapter(created)
            )
            await server.handle_line('{"id":"one","type":"set_session_name","name":"test"}')
            await server.handle_line('{"id":"bad","type":"get_entries","since":"missing"}')
            await server.handle_line('{"id":"next","type":"get_state"}')
            await server.close()
            await output.close()
            return [json.loads(line) for line in lines]

    records = asyncio.run(scenario())
    assert records[0] == {
        "id": "one",
        "type": "response",
        "command": "set_session_name",
        "success": True,
    }
    assert records[1]["success"] is False
    assert records[2]["success"] is True


def test_command_adapter_reuses_session_model_queue_and_control_state(tmp_path: Path) -> None:
    async def scenario() -> tuple[dict[str, object], dict[str, object]]:
        provider = _Models()
        runtime = ModelRuntime(provider=provider, model=provider.models[0])
        created = await create_agent_session(
            CreateAgentSessionOptions(cwd=tmp_path, model_runtime=runtime)
        )
        async with created:
            adapter = RpcCommandAdapter(created)
            await adapter.execute(
                parse_rpc_command({"type": "set_model", "provider": "fake", "modelId": "fake-2"})
            )
            await adapter.execute(parse_rpc_command({"type": "set_thinking_level", "level": "low"}))
            await adapter.execute(parse_rpc_command({"type": "set_steering_mode", "mode": "all"}))
            await adapter.execute(
                parse_rpc_command({"type": "set_auto_compaction", "enabled": False})
            )
            state_value = await adapter.execute(parse_rpc_command({"type": "get_state"}))
            entries_value = await adapter.execute(parse_rpc_command({"type": "get_entries"}))
            assert isinstance(state_value, dict)
            assert isinstance(entries_value, dict)
            return (
                cast("dict[str, object]", state_value),
                cast("dict[str, object]", entries_value),
            )

    state, entries = asyncio.run(scenario())

    model = cast("dict[str, object]", state["model"])
    assert model["id"] == "fake-2"
    assert state["thinkingLevel"] == "low"
    assert state["steeringMode"] == "all"
    assert state["autoCompactionEnabled"] is False
    dumped_entries = cast("list[dict[str, object]]", entries["entries"])
    assert [entry["type"] for entry in dumped_entries] == [
        "model_change",
        "thinking_level_change",
    ]


def test_bash_command_uses_configurable_timeout_and_abort_signal(tmp_path: Path) -> None:
    seen: list[tuple[str, float | None, asyncio.Event | None]] = []

    async def fake_bash(command: str, **kwargs: object) -> BashResult:
        timeout = kwargs.get("timeout")
        abort_event = kwargs.get("abort_event")
        seen.append(
            (
                command,
                timeout if isinstance(timeout, float) else None,
                abort_event if isinstance(abort_event, asyncio.Event) else None,
            )
        )
        return BashResult(
            output="ok",
            exit_code=0,
            aborted=False,
            timed_out=False,
            truncated=False,
            full_output_path=None,
        )

    async def scenario() -> object:
        provider = _Models()
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=ModelRuntime(provider=provider, model=provider.models[0]),
            )
        )
        async with created:
            adapter = RpcCommandAdapter(created, bash_timeout_seconds=321.0, bash_runner=fake_bash)
            result = await adapter.execute(
                parse_rpc_command({"type": "bash", "command": "echo ok"})
            )
            assert created.session.messages[-1].role == "bashExecution"
            entry = created.session.session_manager.entries[-1]
            assert entry.model_dump(by_alias=True)["message"]["output"] == "ok"
            return result

    result = asyncio.run(scenario())

    assert result == {
        "output": "ok",
        "exitCode": 0,
        "aborted": False,
        "timedOut": False,
        "truncated": False,
        "fullOutputPath": None,
    }
    assert seen[0][0:2] == ("echo ok", 321.0)
    assert seen[0][2] is not None


def test_new_session_preserves_memory_mode_and_tree_is_nested(tmp_path: Path) -> None:
    async def scenario() -> None:
        provider = _Models()
        manager = SessionManager.in_memory(
            cwd=tmp_path, session_id="memory", timestamp="2026-09-10T00:00:00.000Z"
        )
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                session_manager=manager,
                model_runtime=ModelRuntime(provider=provider, model=provider.models[0]),
            )
        )
        async with created:
            adapter = RpcCommandAdapter(created)
            first = created.session.set_session_name("first")
            second = created.session.set_session_name("second")
            tree = cast(
                "dict[str, object]", await adapter.execute(parse_rpc_command({"type": "get_tree"}))
            )
            roots = cast("list[dict[str, object]]", tree["tree"])
            assert len(roots) == 1
            assert cast("dict[str, object]", roots[0]["entry"])["id"] == first
            children = cast("list[dict[str, object]]", roots[0]["children"])
            assert cast("dict[str, object]", children[0]["entry"])["id"] == second
            await adapter.execute(parse_rpc_command({"type": "new_session"}))
            assert created.session.session_manager.path is None
            assert created.session.session_manager.header.id != "memory"

    asyncio.run(scenario())


def test_server_prompt_after_new_session_uses_replacement_and_streams_events(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        provider = _Models([fake_assistant_message("new-session-answer")])
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=ModelRuntime(provider=provider, model=provider.models[0]),
            )
        )
        async with created:
            previous = created.session
            lines: list[str] = []
            output = RpcOutput(lines.append)
            await output.start()
            server = RpcServer(session=previous, output=output, commands=RpcCommandAdapter(created))
            await server.handle_line('{"type":"new_session"}')
            await server.handle_line('{"type":"prompt","message":"hello"}')
            await server.wait_for_pending()
            await server.close()
            await output.close()
            assert created.session is not previous
            assert len(created.session.messages) == 2
            assert any(json.loads(line)["type"] == "agent_end" for line in lines)

    asyncio.run(scenario())


def test_export_without_exporter_reports_unavailable(tmp_path: Path) -> None:
    async def scenario() -> None:
        provider = _Models()
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=ModelRuntime(provider=provider, model=provider.models[0]),
            )
        )
        async with created:
            with pytest.raises(RuntimeError, match="HTML exporter is not configured"):
                await RpcCommandAdapter(created).execute(parse_rpc_command({"type": "export_html"}))

    asyncio.run(scenario())


def test_compact_forwards_custom_instructions_to_model(tmp_path: Path) -> None:
    async def scenario() -> None:
        provider = _Models([fake_assistant_message("answer"), fake_assistant_message("summary")])
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=ModelRuntime(provider=provider, model=provider.models[0]),
                compaction_keep_recent_tokens=0,
            )
        )
        async with created:
            await created.session.prompt("remember this task")
            await RpcCommandAdapter(created).execute(
                parse_rpc_command(
                    {"type": "compact", "customInstructions": "Keep exact failing test names"}
                )
            )
            assert "Keep exact failing test names" in repr(provider.calls[-1][1])

    asyncio.run(scenario())


def test_fork_returns_selected_user_text_and_excludes_that_turn(tmp_path: Path) -> None:
    async def scenario() -> None:
        provider = _Models([fake_assistant_message("answer")])
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=ModelRuntime(provider=provider, model=provider.models[0]),
            )
        )
        async with created:
            await created.session.prompt("edit this request")
            stats = cast(
                "dict[str, object]",
                await RpcCommandAdapter(created).execute(
                    parse_rpc_command({"type": "get_session_stats"})
                ),
            )
            assert stats["userMessages"] == 1
            assert stats["assistantMessages"] == 1
            assert stats["totalMessages"] == 2
            assert "tokens" in stats and "cost" in stats
            user_entry = created.session.session_manager.entries[0]
            result = await RpcCommandAdapter(created).execute(
                parse_rpc_command({"type": "fork", "entryId": user_entry.id})
            )
            assert result == {"cancelled": False, "text": "edit this request"}
            assert created.session.messages == ()

    asyncio.run(scenario())


def test_commands_include_prompt_and_skill_resources(tmp_path: Path) -> None:
    prompt = tmp_path / "review.md"
    prompt.write_text("---\ndescription: Review changes\n---\nReview $@", encoding="utf-8")
    skill = tmp_path / "SKILL.md"
    skill.write_text(
        "---\nname: check-project\ndescription: Check project\n---\nRun tests.", encoding="utf-8"
    )

    async def scenario() -> None:
        provider = _Models()
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=tmp_path,
                model_runtime=ModelRuntime(provider=provider, model=provider.models[0]),
                service_overrides=ServiceOverrides(
                    resource_roots=(
                        ResourceRoot(kind="prompt", path=prompt, source="explicit"),
                        ResourceRoot(kind="skill", path=skill, source="explicit"),
                    )
                ),
            )
        )
        async with created:
            result = cast(
                "dict[str, object]",
                await RpcCommandAdapter(created).execute(
                    parse_rpc_command({"type": "get_commands"})
                ),
            )
            commands = cast("list[dict[str, object]]", result["commands"])
            assert {item["name"] for item in commands} == {"review", "skill:check-project"}

    asyncio.run(scenario())
