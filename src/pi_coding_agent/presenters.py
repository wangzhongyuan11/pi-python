"""Stable text and JSONL presentation for headless product modes."""

from __future__ import annotations

import asyncio
import json
from typing import TextIO

from pi_agent import MessageEndEvent, MessageStartEvent, MessageUpdateEvent
from pi_ai import AssistantMessage, TextContent, ToolResultMessage, UserMessage
from pi_ai.wire.events import dump_event
from pi_ai.wire.messages import dump_message

from .agent_session_events import (
    AgentSessionEvent,
    AutoRetryEndEvent,
    AutoRetryStartEvent,
    CompactionEndEvent,
    CompactionStartEvent,
    EntryAppendedEvent,
)
from .session.codec import dump_record


def assistant_text(message: AssistantMessage) -> str:
    return "".join(block.text for block in message.content if isinstance(block, TextContent))


class JsonEventPresenter:
    __slots__ = ("_stdout",)

    def __init__(self, stdout: TextIO) -> None:
        self._stdout = stdout

    def __call__(self, event: AgentSessionEvent, _signal: asyncio.Event) -> None:
        payload: dict[str, object] = {"type": event.type}
        if isinstance(event, AutoRetryStartEvent):
            payload.update(
                attempt=event.attempt,
                maxAttempts=event.max_attempts,
                delayMs=int(event.delay_seconds * 1000),
                errorMessage=event.error_message,
            )
        elif isinstance(event, AutoRetryEndEvent):
            payload.update(success=event.success, attempt=event.attempt)
            if event.final_error is not None:
                payload["finalError"] = event.final_error
        elif isinstance(event, EntryAppendedEvent):
            payload["entry"] = dump_record(event.entry)
        elif isinstance(event, CompactionStartEvent):
            payload["reason"] = event.reason
        elif isinstance(event, CompactionEndEvent):
            payload.update(reason=event.reason, tokensBefore=event.tokens_before)
        elif isinstance(event, MessageStartEvent | MessageEndEvent):
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
