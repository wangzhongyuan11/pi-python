"""Pure conversion from Pi context objects to DeepSeek Chat Completions requests."""

from __future__ import annotations

import json
from typing import Any

from ...context import Context
from ...messages import (
    AssistantMessage,
    ImageContent,
    TextContent,
    ThinkingContent,
    ToolCall,
    UserMessage,
)
from ...models import Model
from ...usage import ModelThinkingLevel

type DeepSeekRequest = dict[str, Any]


class DeepSeekCapabilityError(ValueError):
    """Raised before I/O when a request uses an unsupported model capability."""


def _reject_images(context: Context, model: Model) -> None:
    if "image" in model.input:
        return
    for message in context.messages:
        content = getattr(message, "content", ())
        if isinstance(content, str):
            continue
        if any(isinstance(block, ImageContent) for block in content):
            raise DeepSeekCapabilityError(f"DeepSeek model {model.id} does not support image input")


def _assistant_message(message: AssistantMessage) -> dict[str, Any] | None:
    text = "".join(
        block.text for block in message.content if isinstance(block, TextContent) and block.text
    )
    thinking = "\n".join(
        block.thinking
        for block in message.content
        if isinstance(block, ThinkingContent) and block.thinking
    )
    calls = [block for block in message.content if isinstance(block, ToolCall)]
    if not text and not calls:
        return None

    converted: dict[str, Any] = {
        "role": "assistant",
        "content": text,
        "reasoning_content": thinking,
    }
    if calls:
        converted["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(
                        call.arguments,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                },
            }
            for call in calls
        ]
    return converted


def _convert_messages(context: Context) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    if context.system_prompt:
        converted.append({"role": "system", "content": context.system_prompt})

    for message in context.messages:
        if isinstance(message, UserMessage):
            if isinstance(message.content, str):
                content = message.content
            else:
                content = "\n".join(
                    block.text for block in message.content if isinstance(block, TextContent)
                )
            converted.append({"role": "user", "content": content})
        elif isinstance(message, AssistantMessage):
            assistant = _assistant_message(message)
            if assistant is not None:
                converted.append(assistant)
        else:
            content = "\n".join(
                block.text for block in message.content if isinstance(block, TextContent)
            )
            converted.append(
                {
                    "role": "tool",
                    "content": content or "(no tool output)",
                    "tool_call_id": message.tool_call_id,
                }
            )
    return converted


def _convert_tools(context: Context) -> list[dict[str, Any]] | None:
    if not context.tools:
        return None
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
        for tool in context.tools
    ]


def build_deepseek_request(
    model: Model,
    context: Context,
    *,
    thinking_level: ModelThinkingLevel = "high",
) -> DeepSeekRequest:
    if model.provider != "deepseek":
        raise ValueError("DeepSeek request conversion requires a DeepSeek model")
    if thinking_level not in ("off", "high", "max"):
        raise ValueError("DeepSeek thinking level must be off, high, or max")

    _reject_images(context, model)
    request: DeepSeekRequest = {
        "model": model.id,
        "messages": _convert_messages(context),
        "stream": True,
        "stream_options": {"include_usage": True},
        "max_tokens": model.max_tokens,
        "extra_body": {
            "thinking": {"type": "disabled" if thinking_level == "off" else "enabled"}
        },
    }
    if thinking_level != "off":
        request["reasoning_effort"] = thinking_level
    tools = _convert_tools(context)
    if tools is not None:
        request["tools"] = tools
    return request


__all__ = ["DeepSeekCapabilityError", "DeepSeekRequest", "build_deepseek_request"]
