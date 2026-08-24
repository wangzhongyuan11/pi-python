from __future__ import annotations

import asyncio

from pi_coding_agent.extensions.hooks import HookRunner


def test_sync_and_async_handlers_are_awaited_in_registration_order() -> None:
    async def scenario() -> list[object]:
        runner = HookRunner()
        runner.register("session_start", sync_value)
        runner.register("session_start", async_value)
        return [outcome.value for outcome in await runner.emit("session_start", "x")]

    def sync_value(tag: str) -> str:
        return f"sync-{tag}"

    async def async_value(tag: str) -> str:
        return f"async-{tag}"

    assert asyncio.run(scenario()) == ["sync-x", "async-x"]


def test_third_party_exception_is_isolated_and_remaining_handlers_still_run() -> None:
    async def scenario() -> tuple[list[object], list[object]]:
        runner = HookRunner()

        def boom(_tag: str) -> str:
            raise RuntimeError("third-party bug")

        def after(_tag: str) -> str:
            return "after"

        runner.register("turn_end", boom)
        runner.register("turn_end", after)
        outcomes = await runner.emit("turn_end", "t")

        return (
            [outcome.value for outcome in outcomes],
            [outcome.error for outcome in outcomes if outcome.error is not None],
        )

    values, errors = asyncio.run(scenario())

    assert values == [None, "after"]
    assert len(errors) == 1
    assert isinstance(errors[0], RuntimeError)


def test_cancellation_is_not_swallowed() -> None:
    async def scenario() -> bool:
        runner = HookRunner()

        async def slow(_tag: str) -> None:
            await asyncio.sleep(30)

        runner.register("turn_start", slow)
        task = asyncio.ensure_future(runner.emit("turn_start", "t"))
        await asyncio.sleep(0.01)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return True
        return False

    assert asyncio.run(scenario()) is True
