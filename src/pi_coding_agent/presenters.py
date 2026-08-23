"""Stable text and JSONL presentation for headless product modes."""

from __future__ import annotations

import asyncio
import json
from typing import TextIO

from pi_agent import AgentEvent, MessageEndEvent, MessageStartEvent, MessageUpdateEvent
from pi_ai import AssistantMessage, TextContent, ToolResultMessage, UserMessage
from pi_ai.wire.events import dump_event
from pi_ai.wire.messages import dump_message


def assistant_text(message: AssistantMessage) -> str:
    return "".join(block.text for block in message.content if isinstance(block, TextContent))


class JsonEventPresenter:
    __slots__ = ("_stdout",)

    def __init__(self, stdout: TextIO) -> None:
        self._stdout = stdout

    def __call__(self, event: AgentEvent, _signal: asyncio.Event) -> None:
        payload: dict[str, object] = {"type": event.type}
        if isinstance(event, MessageStartEvent | MessageEndEvent):
            message = event.message
            payload["message"] = (
                dump_message(message)
                if isinstance(message, UserMessage | AssistantMessage | ToolResultMessage)
                else {"role": message.role}
            )
        elif isinstance(event, MessageUpdateEvent):
            payload["assistantMessageEvent"] = dump_event(event.assistant_message_event)
        self._stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        self._stdout.write("\n")


__all__ = ["JsonEventPresenter", "assistant_text"]
