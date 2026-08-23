"""Validation and decoding for AgentMessage payloads stored in Session entries."""

from __future__ import annotations

from typing import cast

from pydantic import ValidationError

from pi_agent import AgentMessage, BashExecutionMessage
from pi_ai.wire.messages import parse_message

from .errors import SessionGraphError
from .models import MessageEntry


def parse_message_entry(entry: MessageEntry) -> AgentMessage:
    role = entry.message.get("role")
    if role in {"user", "assistant", "toolResult"}:
        try:
            return parse_message(entry.message)
        except ValidationError as error:
            raise SessionGraphError(f"invalid message entry: {entry.id}") from error
    if role == "bashExecution":
        payload = entry.message
        try:
            return BashExecutionMessage(
                command=cast("str", payload["command"]),
                output=cast("str", payload["output"]),
                exit_code=cast("int | None", payload.get("exitCode")),
                cancelled=cast("bool", payload["cancelled"]),
                truncated=cast("bool", payload["truncated"]),
                full_output_path=cast("str | None", payload.get("fullOutputPath")),
                exclude_from_context=cast("bool", payload.get("excludeFromContext", False)),
                timestamp=cast("int", payload["timestamp"]),
            )
        except (KeyError, TypeError) as error:
            raise SessionGraphError(f"invalid bash message entry: {entry.id}") from error
    raise SessionGraphError(f"unknown agent message role: {role!r}")


__all__ = ["parse_message_entry"]
