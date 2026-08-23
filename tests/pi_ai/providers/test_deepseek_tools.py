from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from pi_ai import DoneEvent, ErrorEvent, ToolCall
from pi_ai.events import AssistantMessageEvent
from pi_ai.providers.deepseek.models import DEFAULT_DEEPSEEK_MODEL
from pi_ai.providers.deepseek.stream import adapt_deepseek_stream


async def chunks(*values: object) -> AsyncIterator[object]:
    for value in values:
        await asyncio.sleep(0)
        yield value


async def collect(*values: object) -> list[AssistantMessageEvent]:
    stream = adapt_deepseek_stream(
        DEFAULT_DEEPSEEK_MODEL,
        chunks(*values),
        timestamp_ms=123,
    )
    return [event async for event in stream]


def test_assembles_interleaved_tool_calls_by_stream_index() -> None:
    events = asyncio.run(
        collect(
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call-read",
                                    "function": {"name": "re", "arguments": '{"path":'},
                                },
                                {
                                    "index": 1,
                                    "id": "call-ls",
                                    "function": {"name": "ls", "arguments": '{"path":"."'},
                                },
                            ]
                        },
                        "finish_reason": None,
                    }
                ]
            },
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 1,
                                    "function": {"arguments": "}"},
                                },
                                {
                                    "index": 0,
                                    "function": {"name": "ad", "arguments": '"README.md"}'},
                                },
                            ]
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            },
            {
                "choices": [],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                },
            },
        )
    )

    assert [event.type for event in events] == [
        "start",
        "toolcall_start",
        "toolcall_delta",
        "toolcall_start",
        "toolcall_delta",
        "toolcall_delta",
        "toolcall_delta",
        "toolcall_end",
        "toolcall_end",
        "done",
    ]
    assert [event.delta for event in events if event.type == "toolcall_delta"] == [
        '{"path":',
        '{"path":"."',
        "}",
        '"README.md"}',
    ]

    done = events[-1]
    assert isinstance(done, DoneEvent)
    assert done.reason == "toolUse"
    assert done.message.content == (
        ToolCall(id="call-read", name="read", arguments={"path": "README.md"}),
        ToolCall(id="call-ls", name="ls", arguments={"path": "."}),
    )
    assert done.message.usage.total_tokens == 15


def test_invalid_or_non_object_tool_arguments_end_as_provider_error() -> None:
    for arguments in ("{not-json", "[]"):
        events = asyncio.run(
            collect(
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call-bad",
                                        "function": {"name": "read", "arguments": arguments},
                                    }
                                ]
                            },
                            "finish_reason": "tool_calls",
                        }
                    ]
                }
            )
        )

        assert isinstance(events[-1], ErrorEvent)
        assert events[-1].reason == "error"
        assert events[-1].error.error_message is not None
        assert "tool call" in events[-1].error.error_message.lower()
