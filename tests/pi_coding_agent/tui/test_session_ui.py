from __future__ import annotations

import asyncio
from pathlib import Path

from pi_coding_agent.session.catalog import list_sessions, open_session
from pi_coding_agent.session.manager import SessionManager
from pi_coding_agent.tui.session_ui import SessionSelector, fork_from, switch_to

STAMP = "2026-08-24T00:00:00.000Z"


def _make_session(tmp_path: Path, session_id: str) -> None:
    from pi_coding_agent.session.models import MessageEntry

    manager = SessionManager.create(
        cwd=tmp_path,
        session_dir=tmp_path / "sessions",
        session_id=session_id,
        timestamp=STAMP,
    )
    manager.append(
        MessageEntry(
            type="message",
            id=f"{session_id}-1",
            parent_id=None,
            timestamp=STAMP,
            message={
                "role": "assistant",
                "content": [],
                "api": "test",
                "provider": "deepseek",
                "model": "deepseek-v4-pro",
                "usage": {
                    "input": 0,
                    "output": 0,
                    "cacheRead": 0,
                    "cacheWrite": 0,
                    "totalTokens": 0,
                    "cost": {
                        "input": 0.0,
                        "output": 0.0,
                        "cacheRead": 0.0,
                        "cacheWrite": 0.0,
                        "total": 0.0,
                    },
                },
                "stopReason": "stop",
                "timestamp": 1,
            },
        )
    )


def test_selector_navigation_clamps_and_confirms_or_cancels() -> None:
    class Item:
        def __init__(self, name: str) -> None:
            self.name = name

    selector = SessionSelector((Item("one"), Item("two")))

    assert selector.index == 0
    selector.down()
    highlighted = selector.highlighted
    assert highlighted is not None and highlighted.name == "two"
    selector.down()
    assert selector.index == 1
    selector.up()
    selector.up()
    assert selector.index == 0

    confirmed = selector.confirm()
    assert confirmed is not None and confirmed.name == "one"
    assert selector.cancel() is None


def test_empty_selector_confirms_nothing() -> None:
    assert SessionSelector(()).confirm() is None


def test_switch_and_fork_drive_the_runtime_with_opened_manager(tmp_path: Path) -> None:
    _make_session(tmp_path, "alpha")
    catalog = list_sessions(cwd=tmp_path, session_dir=tmp_path / "sessions")
    summary = catalog.sessions[0]

    class FakeRuntime:
        def __init__(self) -> None:
            self.switched: list[str] = []
            self.forked: list[str] = []

        async def switch(self, manager: SessionManager) -> None:
            self.switched.append(manager.header.id)

        async def fork(self, manager: SessionManager) -> None:
            self.forked.append(manager.header.id)

    runtime = FakeRuntime()

    asyncio.run(switch_to(runtime, summary))  # type: ignore[arg-type]
    asyncio.run(fork_from(runtime, summary))  # type: ignore[arg-type]

    opened = open_session(summary.path)
    assert runtime.switched == [opened.header.id]
    assert len(runtime.forked) == 1
    assert runtime.forked[0] != opened.header.id
