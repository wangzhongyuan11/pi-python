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


def _user_content(message: UserMessage) -> str | list[dict[str, Any]]:
    if isinstance(message.content, str):
        return message.content
    parts: list[dict[str, Any]] = []
    text_chunks: list[str] = []
    for block in message.content:
        if isinstance(block, TextContent):
            text_chunks.append(block.text)
        elif isinstance(block, ImageContent):
            parts.append({"type": "text", "text": "\n".join(text_chunks)} if text_chunks else None)
            text_chunks.clear()
            parts.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{block.mime_type};base64,{block.data}"},
                }
            )
    if text_chunks:
        parts.append({"type": "text", "text": "\n".join(text_chunks)})
    if not any(part is not None for part in parts):
        return ""
    content = [part for part in parts if part is not None]
    if len(content) == 1 and content[0]["type"] == "text":
        return content[0]["text"]
    return content


def _convert_messages(context: Context) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    if context.system_prompt:
        converted.append({"role": "system", "content": context.system_prompt})

    for message in context.messages:
        if isinstance(message, UserMessage):
            converted.append({"role": "user", "content": _user_content(message)})
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
    max_tokens: int | None = None,
) -> DeepSeekRequest:
    if model.provider != "deepseek":
        raise ValueError("DeepSeek request conversion requires a DeepSeek model")
    if thinking_level not in ("off", "high", "max"):
        raise ValueError("DeepSeek thinking level must be off, high, or max")
    if max_tokens is not None and (max_tokens <= 0 or max_tokens > model.max_tokens):
        raise ValueError("DeepSeek max_tokens must be positive and within the model limit")

    _reject_images(context, model)
    request: DeepSeekRequest = {
        "model": model.id,
        "messages": _convert_messages(context),
        "stream": True,
        "stream_options": {"include_usage": True},
        "max_tokens": model.max_tokens if max_tokens is None else max_tokens,
        "extra_body": {"thinking": {"type": "disabled" if thinking_level == "off" else "enabled"}},
    }
    if thinking_level != "off":
        request["reasoning_effort"] = thinking_level
    tools = _convert_tools(context)
    if tools is not None:
        request["tools"] = tools
    return request


__all__ = ["DeepSeekCapabilityError", "DeepSeekRequest", "build_deepseek_request"]
