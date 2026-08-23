from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from pi_coding_agent.tools.mutation_queue import FileMutationQueue


def test_same_path_operations_are_serialized(tmp_path: Path) -> None:
    async def scenario() -> list[str]:
        queue = FileMutationQueue()
        path = tmp_path / "same.txt"
        entered = asyncio.Event()
        release = asyncio.Event()
        order: list[str] = []

        async def first() -> None:
            order.append("first-start")
            entered.set()
            await release.wait()
            order.append("first-end")

        async def second() -> None:
            order.append("second")

        first_task = asyncio.create_task(queue.run(path, cwd=tmp_path, operation=first))
        await entered.wait()
        second_task = asyncio.create_task(queue.run(path, cwd=tmp_path, operation=second))
        await asyncio.sleep(0)
        assert order == ["first-start"]
        release.set()
        await asyncio.gather(first_task, second_task)
        return order

    assert asyncio.run(scenario()) == ["first-start", "first-end", "second"]


def test_symlink_aliases_share_one_queue(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    target.write_text("content", encoding="utf-8")
    alias = tmp_path / "alias.txt"
    try:
        alias.symlink_to(target)
    except OSError as error:
        pytest.skip(f"symlink creation is unavailable: {error}")

    async def scenario() -> list[str]:
        queue = FileMutationQueue()
        entered = asyncio.Event()
        release = asyncio.Event()
        order: list[str] = []

        async def first() -> None:
            order.append("target-start")
            entered.set()
            await release.wait()
            order.append("target-end")

        async def second() -> None:
            order.append("alias")

        first_task = asyncio.create_task(queue.run(target, cwd=tmp_path, operation=first))
        await entered.wait()
        second_task = asyncio.create_task(queue.run(alias, cwd=tmp_path, operation=second))
        await asyncio.sleep(0)
        assert order == ["target-start"]
        release.set()
        await asyncio.gather(first_task, second_task)
        return order

    assert asyncio.run(scenario()) == ["target-start", "target-end", "alias"]


def test_different_paths_can_run_concurrently(tmp_path: Path) -> None:
    async def scenario() -> set[str]:
        queue = FileMutationQueue()
        both_entered = asyncio.Event()
        release = asyncio.Event()
        active: set[str] = set()

        async def operation(name: str) -> None:
            active.add(name)
            if len(active) == 2:
                both_entered.set()
            await release.wait()

        tasks = [
            asyncio.create_task(
                queue.run(
                    tmp_path / f"{name}.txt",
                    cwd=tmp_path,
                    operation=lambda name=name: operation(name),
                )
            )
            for name in ("one", "two")
        ]
        await asyncio.wait_for(both_entered.wait(), timeout=1)
        snapshot = set(active)
        release.set()
        await asyncio.gather(*tasks)
        return snapshot

    assert asyncio.run(scenario()) == {"one", "two"}


def test_failed_operation_releases_the_next_waiter(tmp_path: Path) -> None:
    async def scenario() -> str:
        queue = FileMutationQueue()
        path = tmp_path / "same.txt"
        entered = asyncio.Event()
        release = asyncio.Event()

        async def failing() -> None:
            entered.set()
            await release.wait()
            raise RuntimeError("failure")

        async def succeeding() -> str:
            return "completed"

        failed = asyncio.create_task(queue.run(path, cwd=tmp_path, operation=failing))
        await entered.wait()
        succeeded = asyncio.create_task(queue.run(path, cwd=tmp_path, operation=succeeding))
        release.set()
        with pytest.raises(RuntimeError, match="failure"):
            await failed
        return await succeeded

    assert asyncio.run(scenario()) == "completed"
