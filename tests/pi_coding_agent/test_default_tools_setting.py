"""Settings-driven default tool selection (P11.5-T04)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from pi_ai import FakeProvider, fake_assistant_message
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.ports import InMemorySettings
from pi_coding_agent.sdk import CreateAgentSessionOptions, create_agent_session
from pi_coding_agent.services import ServiceOverrides
from pi_coding_agent.session.manager import SessionManager


def _names(settings_payload: dict[str, Any], **options: Any) -> tuple[str, ...]:
    async def scenario() -> tuple[str, ...]:
        provider = FakeProvider([fake_assistant_message("ok")])
        created = await create_agent_session(
            CreateAgentSessionOptions(
                cwd=Path.cwd(),
                model_runtime=ModelRuntime(provider=provider, model=provider.models[0]),
                session_manager=SessionManager.in_memory(
                    cwd=Path.cwd(),
                    session_id="default-tools",
                    timestamp="2026-08-30T00:00:00.000Z",
                ),
                service_overrides=ServiceOverrides(settings=InMemorySettings(settings_payload)),
                agent_clock=lambda: 1,
                **options,
            )
        )
        async with created:
            return tuple(tool.name for tool in created.session.agent.state.tools)

    return asyncio.run(scenario())


def test_default_tools_setting_replaces_the_builtin_default() -> None:
    assert _names({"defaultTools": ["read", "grep"]}) == ("read", "grep")


def test_cli_tool_names_win_over_the_settings_default() -> None:
    assert _names(
        {"defaultTools": ["read", "grep"]},
        tool_names=("read", "bash"),
    ) == ("read", "bash")


def test_no_tools_wins_over_the_settings_default() -> None:
    assert _names({"defaultTools": ["read", "grep"]}, no_tools="all") == ()


def test_unknown_names_in_the_setting_are_ignored() -> None:
    names = _names({"defaultTools": ["read", "grep", "mystery"]})
    assert names == ("read", "grep")
