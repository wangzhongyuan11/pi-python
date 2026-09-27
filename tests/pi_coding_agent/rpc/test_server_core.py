from __future__ import annotations

import asyncio
import json
from collections.abc import Callable

import pytest

from pi_coding_agent.rpc.framing import JsonlFramer, serialize_json_line
from pi_coding_agent.rpc.server import RpcOutput, RpcServer


def test_framer_splits_only_lf_and_accepts_final_record() -> None:
    framer = JsonlFramer()

    assert framer.feed('{"message":"a\u2028b"}\r\n{"type":') == ['{"message":"a\u2028b"}']
    assert framer.feed('"abort"}') == []
    assert framer.finish() == ['{"type":"abort"}']
    assert serialize_json_line({"text": "line\u2029separator"}).endswith("\n")


class _Session:
    def __init__(self) -> None:
        self.listener: Callable[..., object] | None = None
        self.prompts: list[str] = []
        self.aborted = False

    def subscribe(self, listener: Callable[..., object]) -> Callable[[], None]:
        self.listener = listener
        return lambda: None

    async def prompt(self, message: str) -> None:
        self.prompts.append(message)

    def abort(self) -> None:
        self.aborted = True


def test_server_keeps_protocol_errors_on_stdout_and_continues() -> None:
    async def scenario() -> tuple[list[object], _Session]:
        lines: list[str] = []
        session = _Session()
        output = RpcOutput(lines.append)
        server = RpcServer(session=session, output=output)
        await output.start()

        await server.handle_line("not-json")
        await server.handle_line('{"id":"a","type":"abort"}')
        await server.wait_for_pending()
        await output.close()
        return [json.loads(line) for line in lines], session

    records, session = asyncio.run(scenario())
    assert isinstance(records[0], dict)
    assert records[0]["type"] == "response"
    assert records[0]["success"] is False
    assert records[1] == {"id": "a", "type": "response", "command": "abort", "success": True}
    assert session.aborted is True


def test_bounded_output_applies_backpressure_to_producers() -> None:
    async def scenario() -> bool:
        release = asyncio.Event()

        async def slow_write(_line: str) -> None:
            await release.wait()

        output = RpcOutput(slow_write, capacity=1)
        await output.start()
        await output.emit({"type": "first"})
        await asyncio.sleep(0)
        await output.emit({"type": "second"})
        blocked = asyncio.create_task(output.emit({"type": "third"}))
        await asyncio.sleep(0)
        was_blocked = not blocked.done()
        release.set()
        await blocked
        await output.close()
        return was_blocked

    assert asyncio.run(scenario()) is True


def test_output_writer_failure_does_not_hang_close() -> None:
    async def scenario() -> None:
        def broken_write(_line: str) -> None:
            raise BrokenPipeError("client disconnected")

        output = RpcOutput(broken_write)
        await output.start()
        await output.emit({"type": "first"})
        await output.emit({"type": "second"})
        with pytest.raises(BrokenPipeError):
            await asyncio.wait_for(output.close(), 0.2)

    asyncio.run(scenario())
