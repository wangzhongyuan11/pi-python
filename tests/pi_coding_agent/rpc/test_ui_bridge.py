from __future__ import annotations

import asyncio
import json

import pytest

from pi_coding_agent.rpc.server import RpcOutput, RpcServer
from pi_coding_agent.rpc.ui_bridge import RpcUiBridge

from .test_server_core import _Session


def test_ui_correlates_out_of_order_responses_and_ignores_duplicates() -> None:
    async def scenario() -> None:
        frames: list[dict[str, object]] = []

        async def send(frame: dict[str, object]) -> None:
            frames.append(frame)

        ui = RpcUiBridge(send)
        first = asyncio.create_task(ui.input("Name"))
        second = asyncio.create_task(ui.confirm("Continue?"))
        await asyncio.sleep(0)
        assert not ui.handle_response(
            {"type": "extension_ui_response", "id": "unknown", "value": "x"}
        )
        assert not ui.handle_response(
            {"type": "extension_ui_response", "id": frames[1]["id"], "value": "wrong type"}
        )
        assert ui.handle_response(
            {"type": "extension_ui_response", "id": frames[1]["id"], "confirmed": True}
        )
        assert await second is True
        assert not first.done()
        assert ui.handle_response(
            {"type": "extension_ui_response", "id": frames[0]["id"], "value": "Ada"}
        )
        assert await first == "Ada"
        assert not ui.handle_response(
            {"type": "extension_ui_response", "id": frames[0]["id"], "value": "duplicate"}
        )
        await ui.close()

    asyncio.run(scenario())


def test_ui_timeout_cancellation_and_disconnect_release_waiters() -> None:
    async def scenario() -> None:
        frames: list[dict[str, object]] = []

        async def send(frame: dict[str, object]) -> None:
            frames.append(frame)

        ui = RpcUiBridge(send, timeout_seconds=0.01)
        assert await ui.input("Timeout") is None
        assert not ui.handle_response(
            {"type": "extension_ui_response", "id": frames[0]["id"], "value": "late"}
        )
        selected = asyncio.create_task(ui.select("Pick", ("a", "b")))
        await asyncio.sleep(0)
        ui.handle_response(
            {"type": "extension_ui_response", "id": frames[-1]["id"], "cancelled": True}
        )
        assert await selected is None
        pending = asyncio.create_task(ui.confirm("Disconnect"))
        await asyncio.sleep(0)
        await ui.close()
        assert await pending is False
        with pytest.raises(RuntimeError, match="closed"):
            await ui.input("After close")

    asyncio.run(scenario())


def test_ui_rejects_invalid_selection_and_emits_serializable_updates() -> None:
    async def scenario() -> None:
        frames: list[dict[str, object]] = []

        async def send(frame: dict[str, object]) -> None:
            frames.append(frame)

        ui = RpcUiBridge(send)
        selected = asyncio.create_task(ui.select("Pick", ("a", "b")))
        await asyncio.sleep(0)
        ui.handle_response(
            {"type": "extension_ui_response", "id": frames[0]["id"], "value": "outside"}
        )
        assert await selected is None
        ui.notify("Ready", level="info")
        ui.set_status("build", "done")
        ui.set_widget("tasks", ("one", "two"))
        ui.set_title("Project")
        ui.set_editor_text("next task")
        await ui.flush()
        assert [frame["method"] for frame in frames[1:]] == [
            "notify",
            "setStatus",
            "setWidget",
            "setTitle",
            "set_editor_text",
        ]
        assert all(frame["type"] == "extension_ui_request" for frame in frames)
        json.dumps(frames)
        await ui.close()

    asyncio.run(scenario())


def test_server_routes_ui_responses_without_command_acknowledgement() -> None:
    async def scenario() -> None:
        lines: list[str] = []
        output = RpcOutput(lines.append)
        await output.start()
        ui = RpcUiBridge(output.emit)
        server = RpcServer(session=_Session(), output=output, ui=ui)
        pending = asyncio.create_task(ui.input("Name"))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        request = json.loads(lines[0])
        await server.handle_line(
            json.dumps({"type": "extension_ui_response", "id": request["id"], "value": "Ada"})
        )
        assert await pending == "Ada"
        await server.close()
        await output.close()
        assert len(lines) == 1

    asyncio.run(scenario())


def test_ui_bounds_updates_and_surfaces_transport_failure() -> None:
    async def scenario() -> None:
        release = asyncio.Event()

        async def blocked_send(_frame: dict[str, object]) -> None:
            await release.wait()

        ui = RpcUiBridge(blocked_send, capacity=1)
        ui.notify("first")
        with pytest.raises(RuntimeError, match="too many"):
            ui.notify("second")
        await asyncio.wait_for(ui.close(), 1)

        async def broken_send(_frame: dict[str, object]) -> None:
            raise BrokenPipeError("disconnected")

        broken = RpcUiBridge(broken_send)
        with pytest.raises(BrokenPipeError):
            await broken.input("Name")
        broken.notify("first")
        with pytest.raises(BrokenPipeError):
            await broken.flush()
        await broken.close()

    asyncio.run(scenario())


def test_cancelled_ui_task_does_not_consume_request_capacity() -> None:
    async def scenario() -> None:
        frames: list[dict[str, object]] = []

        async def send(frame: dict[str, object]) -> None:
            frames.append(frame)

        ui = RpcUiBridge(send, capacity=1)
        pending = asyncio.create_task(ui.input("First"))
        await asyncio.sleep(0)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        next_request = asyncio.create_task(ui.editor("Second", prefill="draft"))
        await asyncio.sleep(0)
        ui.handle_response(
            {"type": "extension_ui_response", "id": frames[-1]["id"], "value": "edited"}
        )
        assert await next_request == "edited"
        await ui.close()

    asyncio.run(scenario())
