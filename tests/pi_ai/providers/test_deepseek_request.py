from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from pi_ai import (
    AssistantMessage,
    Context,
    ImageContent,
    Message,
    TextContent,
    ThinkingContent,
    Tool,
    ToolCall,
    ToolResultMessage,
    Usage,
    UsageCost,
    UserMessage,
)
from pi_ai.providers.deepseek.models import DEFAULT_DEEPSEEK_MODEL
from pi_ai.providers.deepseek.request import DeepSeekCapabilityError, build_deepseek_request


class ReadParams(BaseModel):
    path: str


def zero_usage() -> Usage:
    return Usage(
        input=0,
        output=0,
        cache_read=0,
        cache_write=0,
        total_tokens=0,
        cost=UsageCost(input=0, output=0, cache_read=0, cache_write=0, total=0),
    )


def test_converts_system_roles_tools_and_thinking_history() -> None:
    tool = Tool(name="read", description="Read a file", parameter_type=ReadParams)
    assistant = AssistantMessage(
        content=(
            ThinkingContent(thinking="inspect first"),
            TextContent(text="I will read it."),
            ToolCall(id="call-1", name="read", arguments={"path": "README.md"}),
        ),
        api="openai-completions",
        provider="deepseek",
        model="deepseek-v4-pro",
        usage=zero_usage(),
        stop_reason="toolUse",
        timestamp=2,
    )
    result = ToolResultMessage(
        tool_call_id="call-1",
        tool_name="read",
        content=(TextContent(text="contents"),),
        is_error=False,
        timestamp=3,
    )
    context = Context(
        system_prompt="You are concise.",
        messages=(
            UserMessage(content="Read it", timestamp=1),
            assistant,
            result,
        ),
        tools=(tool,),
    )

    request = build_deepseek_request(
        DEFAULT_DEEPSEEK_MODEL,
        context,
        thinking_level="max",
    )

    assert request["model"] == "deepseek-v4-pro"
    assert request["stream"] is True
    assert request["stream_options"] == {"include_usage": True}
    assert request["max_tokens"] == 384_000
    assert request["reasoning_effort"] == "max"
    assert request["extra_body"] == {"thinking": {"type": "enabled"}}
    assert request["messages"] == [
        {"role": "system", "content": "You are concise."},
        {"role": "user", "content": "Read it"},
        {
            "role": "assistant",
            "content": "I will read it.",
            "reasoning_content": "inspect first",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "read", "arguments": '{"path":"README.md"}'},
                }
            ],
        },
        {"role": "tool", "content": "contents", "tool_call_id": "call-1"},
    ]
    tools = request["tools"]
    assert isinstance(tools, list)
    assert tools[0]["function"]["name"] == "read"
    assert tools[0]["function"]["parameters"]["required"] == ["path"]


def test_disables_thinking_without_sending_reasoning_effort() -> None:
    request = build_deepseek_request(
        DEFAULT_DEEPSEEK_MODEL,
        Context(messages=(UserMessage(content="hello", timestamp=1),)),
        thinking_level="off",
    )

    assert request["extra_body"] == {"thinking": {"type": "disabled"}}
    assert "reasoning_effort" not in request


def test_empty_tool_output_gets_a_stable_placeholder() -> None:
    context = Context(
        messages=(
            ToolResultMessage(
                tool_call_id="call-1",
                tool_name="read",
                content=(),
                is_error=False,
                timestamp=1,
            ),
        )
    )

    request = build_deepseek_request(DEFAULT_DEEPSEEK_MODEL, context)

    assert request["messages"] == [
        {"role": "tool", "content": "(no tool output)", "tool_call_id": "call-1"}
    ]


@pytest.mark.parametrize(
    "message",
    [
        UserMessage(
            content=(ImageContent(data="AAAA", mime_type="image/png"),),
            timestamp=1,
        ),
        ToolResultMessage(
            tool_call_id="call-1",
            tool_name="read",
            content=(ImageContent(data="AAAA", mime_type="image/png"),),
            is_error=False,
            timestamp=1,
        ),
    ],
)
def test_rejects_images_before_building_a_text_model_request(message: Message) -> None:
    with pytest.raises(DeepSeekCapabilityError, match="does not support image input"):
        build_deepseek_request(DEFAULT_DEEPSEEK_MODEL, Context(messages=(message,)))


def test_tool_arguments_are_compact_valid_json() -> None:
    assistant = AssistantMessage(
        content=(ToolCall(id="call-1", name="read", arguments={"path": "中文 文件.md"}),),
        api="openai-completions",
        provider="deepseek",
        model="deepseek-v4-pro",
        usage=zero_usage(),
        stop_reason="toolUse",
        timestamp=1,
    )

    request = build_deepseek_request(DEFAULT_DEEPSEEK_MODEL, Context(messages=(assistant,)))
    arguments = request["messages"][0]["tool_calls"][0]["function"]["arguments"]

    assert json.loads(arguments) == {"path": "中文 文件.md"}
