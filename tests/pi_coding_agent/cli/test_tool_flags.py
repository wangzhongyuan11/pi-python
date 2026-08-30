"""CLI tool selection flags and product wiring (P11.5-T03)."""

from __future__ import annotations

import asyncio
from importlib.metadata import version
from pathlib import Path
from typing import Any

from pi_ai import FakeProvider, fake_assistant_message
from pi_coding_agent.cli.main import tool_selection_from_arguments
from pi_coding_agent.cli.parser import create_run_parser
from pi_coding_agent.model_runtime import ModelRuntime
from pi_coding_agent.sdk import CreateAgentSessionOptions, create_agent_session
from pi_coding_agent.session.manager import SessionManager
from pi_coding_agent.tools.registry import ALL_TOOL_NAMES, expand_tool_selection


def _parse(argv: list[str]):
    parser = create_run_parser(version=version("pi-python"))
    return parser.parse_args([*argv, "hello"])


class TestParserToolFlags:
    def test_tools_accepts_all_and_name_lists(self) -> None:
        assert _parse(["--tools", "all"]).tools == "all"
        assert _parse(["-t", "read,bash"]).tools == "read,bash"

    def test_exclude_tools_and_disable_flags_parse(self) -> None:
        arguments = _parse(["--exclude-tools", "bash,write"])
        assert arguments.exclude_tools == "bash,write"
        arguments = _parse(["-nt"])
        assert arguments.no_tools is True
        arguments = _parse(["-nbt"])
        assert arguments.no_builtin_tools is True


class TestExpandToolSelection:
    def test_all_expands_to_the_full_builtin_set(self) -> None:
        assert expand_tool_selection("all") == tuple(ALL_TOOL_NAMES)

    def test_explicit_names_pass_through(self) -> None:
        assert expand_tool_selection("read,grep") == ("read", "grep")


class TestArgumentMapping:
    def test_tool_flags_map_to_sdk_selection_fields(self) -> None:
        selection = tool_selection_from_arguments(_parse(["--tools", "all"]))
        assert selection.tool_names == tuple(ALL_TOOL_NAMES)
        assert selection.no_tools is None
        selection = tool_selection_from_arguments(_parse(["-nt"]))
        assert selection.no_tools == "all"
        selection = tool_selection_from_arguments(_parse(["-nbt"]))
        assert selection.no_tools == "builtin"
        selection = tool_selection_from_arguments(_parse(["--exclude-tools", "bash"]))
        assert selection.exclude_tools == ("bash",)


def _manager(cwd: Path) -> SessionManager:
    return SessionManager.in_memory(
        cwd=cwd,
        session_id="tool-flags",
        timestamp="2026-08-30T00:00:00.000Z",
    )


class TestSdkToolSelection:
    def _runtime(self) -> ModelRuntime:
        provider = FakeProvider([fake_assistant_message("ok")])
        return ModelRuntime(provider=provider, model=provider.models[0])

    def _names(self, **options: Any) -> tuple[str, ...]:
        async def scenario() -> tuple[str, ...]:
            created = await create_agent_session(
                CreateAgentSessionOptions(
                    cwd=Path.cwd(),
                    model_runtime=self._runtime(),
                    session_manager=_manager(Path.cwd()),
                    agent_clock=lambda: 1,
                    **options,
                )
            )
            async with created:
                return tuple(tool.name for tool in created.session.agent.state.tools)

        return asyncio.run(scenario())

    def test_default_composition_keeps_four_coding_tools(self) -> None:
        assert self._names() == ("read", "bash", "edit", "write")

    def test_tools_allowlist_selects_builtin_tools_with_real_operations(self) -> None:
        assert self._names(tool_names=("read", "grep", "find", "ls")) == (
            "read",
            "grep",
            "find",
            "ls",
        )

    def test_no_tools_all_disables_builtin_and_extension_tools(self) -> None:
        assert self._names(no_tools="all") == ()

    def test_exclude_tools_wins_over_defaults(self) -> None:
        assert self._names(exclude_tools=("bash",)) == ("read", "edit", "write")
