from __future__ import annotations

import asyncio

import pytest

from pi_coding_agent.extensions.api import ExtensionAPI
from pi_coding_agent.extensions.registry import RegistryConflictError
from pi_coding_agent.tui.commands import CommandDispatcher, CommandOutcome, CommandSpec


def test_slash_lines_dispatch_to_registered_handlers() -> None:
    dispatcher = CommandDispatcher()
    dispatcher.register(
        CommandSpec(
            name="help",
            source="builtin",
            handler=lambda _args: CommandOutcome(kind="message", text="help text"),
        )
    )
    dispatcher.register(
        CommandSpec(
            name="model",
            source="builtin",
            handler=lambda _args: CommandOutcome(kind="message", text="/model"),
        )
    )

    assert asyncio.run(dispatcher.dispatch("not-a-command")) is None
    outcome = asyncio.run(dispatcher.dispatch("/help extra"))
    assert outcome is not None and outcome.text == "help text"
    unknown = asyncio.run(dispatcher.dispatch("/nope"))
    assert unknown is not None and unknown.kind == "error"


def test_duplicate_command_names_conflict() -> None:
    dispatcher = CommandDispatcher()
    spec = CommandSpec(name="same", source="builtin", handler=lambda _args: None)

    dispatcher.register(spec)
    with pytest.raises(RegistryConflictError):
        dispatcher.register(spec)


def test_handler_exception_is_isolated_into_error_outcome() -> None:
    def boom(_args: str) -> CommandOutcome:
        raise RuntimeError("handler bug")

    dispatcher = CommandDispatcher()
    dispatcher.register(CommandSpec(name="boom", source="ext", handler=boom))

    outcome = asyncio.run(dispatcher.dispatch("/boom"))
    assert outcome is not None
    assert outcome.kind == "error"
    assert "handler bug" in outcome.text


def test_extension_dialog_can_be_cancelled_while_awaiting_input() -> None:
    from pi_coding_agent.tui.extension_ui import DialogBridge

    async def scenario() -> str | None:
        bridge = DialogBridge()

        async def ask() -> str | None:
            return await bridge.show_dialog("approve?")

        task = asyncio.ensure_future(ask())
        await asyncio.sleep(0.01)
        cancelled = bridge.cancel_pending()
        return await task if not cancelled else await task

    assert asyncio.run(scenario()) is None


def test_dispatcher_imports_executable_extension_commands() -> None:
    api = ExtensionAPI("sample")

    def shout(args: str) -> str:
        return args.upper()

    api.define_command("shout", shout)

    dispatcher = CommandDispatcher.from_registry(api.registry)
    outcome = asyncio.run(dispatcher.dispatch("/shout hello"))

    assert outcome == CommandOutcome(kind="message", text="HELLO")


def test_dialog_exposes_prompt_and_targets_response_by_request_id() -> None:
    from pi_coding_agent.tui.extension_ui import DialogBridge

    async def scenario() -> str | None:
        bridge = DialogBridge()
        task = asyncio.create_task(bridge.show_dialog("approve this operation?"))
        await asyncio.sleep(0)
        pending = bridge.pending
        assert len(pending) == 1
        assert pending[0].text == "approve this operation?"
        assert bridge.respond("yes", request_id=pending[0].id)
        return await task

    assert asyncio.run(scenario()) == "yes"
