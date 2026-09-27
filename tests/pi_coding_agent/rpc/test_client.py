from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

from pi_coding_agent.rpc.client import RpcClient, RpcClientError


def test_client_correlates_concurrent_responses_and_delivers_events() -> None:
    async def scenario() -> None:
        reader = asyncio.StreamReader()
        sent: list[dict[str, object]] = []

        async def write(line: str) -> None:
            sent.append(json.loads(line))

        client = RpcClient(reader, write)
        await client.start()
        first = asyncio.create_task(client.request("get_messages"))
        second = asyncio.create_task(client.request("get_commands"))
        await asyncio.sleep(0)
        reader.feed_data(
            (
                json.dumps(
                    {
                        "type": "response",
                        "id": sent[1]["id"],
                        "command": "get_commands",
                        "success": True,
                        "data": {"commands": []},
                    }
                )
                + "\n"
            ).encode()
        )
        reader.feed_data(b'{"type":"agent_end","messages":[]}\n')
        reader.feed_data(
            (
                json.dumps(
                    {
                        "type": "response",
                        "id": sent[0]["id"],
                        "command": "get_messages",
                        "success": True,
                        "data": {"messages": []},
                    }
                )
                + "\n"
            ).encode()
        )
        assert await first == {"messages": []}
        assert await second == {"commands": []}
        assert (await client.next_event())["type"] == "agent_end"
        await client.close()

    asyncio.run(scenario())


def test_client_request_timeout_and_error_leave_other_requests_usable() -> None:
    async def scenario() -> None:
        reader = asyncio.StreamReader()

        async def write(line: str) -> None:
            command = json.loads(line)
            if command["type"] != "get_state":
                reader.feed_data(
                    (
                        json.dumps(
                            {
                                "type": "response",
                                "id": command["id"],
                                "command": command["type"],
                                "success": False,
                                "error": "unavailable",
                            }
                        )
                        + "\n"
                    ).encode()
                )

        client = RpcClient(reader, write)
        await client.start()
        with pytest.raises(TimeoutError):
            await client.request("get_state", timeout=0.01)
        with pytest.raises(RpcClientError, match="unavailable"):
            await client.request("get_messages")
        await client.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("invalid", [b"", b"not-json\n", b'{"type":"response","success":true}\n'])
def test_client_eof_or_bad_frame_fails_pending_requests(invalid: bytes) -> None:
    async def scenario() -> None:
        reader = asyncio.StreamReader()

        async def write(_line: str) -> None:
            reader.feed_data(invalid)
            reader.feed_eof()

        client = RpcClient(reader, write)
        await client.start()
        with pytest.raises(RpcClientError):
            await asyncio.wait_for(client.request("get_state"), 1)
        await client.close()

    asyncio.run(scenario())


def test_client_close_releases_requests_and_event_waiters() -> None:
    async def scenario() -> None:
        reader = asyncio.StreamReader()
        shutdowns: list[bool] = []

        async def write(_line: str) -> None:
            pass

        async def shutdown() -> None:
            shutdowns.append(True)

        client = RpcClient(reader, write, shutdown=shutdown)
        await client.start()
        request = asyncio.create_task(client.request("get_state"))
        event = asyncio.create_task(client.next_event())
        await asyncio.sleep(0)
        await client.close()
        await client.close()
        for task in (request, event):
            with pytest.raises(RpcClientError, match="closed"):
                await task
        assert shutdowns == [True]

    asyncio.run(scenario())


def test_client_launches_and_closes_real_protocol_subprocess(tmp_path: Path) -> None:
    async def scenario() -> None:
        script = (
            "import sys,json\n"
            "for line in sys.stdin:\n"
            " c=json.loads(line)\n"
            " print(json.dumps(dict(type='response',id=c['id'],command=c['type'],"
            "success=True,data={'messages':[]})),flush=True)\n"
        )
        client = await RpcClient.launch(
            (sys.executable, "-u", "-c", script), cwd=tmp_path, shutdown_timeout=1
        )
        async with client:
            assert await client.request("get_messages") == {"messages": []}
        with pytest.raises(RpcClientError, match="closed"):
            await client.request("get_messages")

    asyncio.run(scenario())


def test_client_event_overflow_fails_without_starving_pending_response() -> None:
    async def scenario() -> None:
        reader = asyncio.StreamReader()

        async def write(_line: str) -> None:
            reader.feed_data(b'{"type":"agent_start"}\n' * 2)

        client = RpcClient(reader, write, event_capacity=1)
        await client.start()
        with pytest.raises(RpcClientError, match="capacity"):
            await asyncio.wait_for(client.request("get_state"), 1)
        await client.close()

    asyncio.run(scenario())
