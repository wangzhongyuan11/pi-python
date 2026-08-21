"""Agent transcript messages and the default provider conversion."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from pi_ai import (
    AssistantMessage,
    ImageContent,
    JsonValue,
    Message,
    TextContent,
    ToolResultMessage,
    UserMessage,
)

COMPACTION_SUMMARY_PREFIX = (
    "The conversation history before this point was compacted into the following summary:\n\n"
    "<summary>\n"
)
COMPACTION_SUMMARY_SUFFIX = "\n</summary>"
BRANCH_SUMMARY_PREFIX = (
    "The following is a summary of a branch that this conversation came back from:\n\n<summary>\n"
)
BRANCH_SUMMARY_SUFFIX = "</summary>"


@dataclass(frozen=True, slots=True, kw_only=True)
class BashExecutionMessage:
    command: str
    output: str
    exit_code: int | None
    cancelled: bool
    truncated: bool
    timestamp: int
    full_output_path: str | None = None
    exclude_from_context: bool = False
    role: Literal["bashExecution"] = field(default="bashExecution", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class CustomMessage:
    custom_type: str
    content: str | tuple[TextContent | ImageContent, ...]
    display: bool
    timestamp: int
    details: JsonValue = None
    role: Literal["custom"] = field(default="custom", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class BranchSummaryMessage:
    summary: str
    from_id: str
    timestamp: int
    role: Literal["branchSummary"] = field(default="branchSummary", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class CompactionSummaryMessage:
    summary: str
    tokens_before: int
    timestamp: int
    role: Literal["compactionSummary"] = field(default="compactionSummary", init=False)


type AgentMessage = (
    Message | BashExecutionMessage | CustomMessage | BranchSummaryMessage | CompactionSummaryMessage
)


def bash_execution_to_text(message: BashExecutionMessage) -> str:
    text = f"Ran `{message.command}`\n"
    text += f"```\n{message.output}\n```" if message.output else "(no output)"
    if message.cancelled:
        text += "\n\n(command cancelled)"
    elif message.exit_code not in (None, 0):
        text += f"\n\nCommand exited with code {message.exit_code}"
    if message.truncated and message.full_output_path:
        text += f"\n\n[Output truncated. Full output: {message.full_output_path}]"
    return text


def default_convert_to_llm(messages: Sequence[AgentMessage]) -> tuple[Message, ...]:
    converted: list[Message] = []
    for message in messages:
        if isinstance(message, UserMessage | AssistantMessage | ToolResultMessage):
            converted.append(message)
        elif isinstance(message, BashExecutionMessage):
            if not message.exclude_from_context:
                converted.append(
                    UserMessage(
                        content=(TextContent(text=bash_execution_to_text(message)),),
                        timestamp=message.timestamp,
                    )
                )
        elif isinstance(message, CustomMessage):
            content = (
                (TextContent(text=message.content),)
                if isinstance(message.content, str)
                else message.content
            )
            converted.append(UserMessage(content=content, timestamp=message.timestamp))
        elif isinstance(message, BranchSummaryMessage):
            converted.append(
                UserMessage(
                    content=(
                        TextContent(
                            text=BRANCH_SUMMARY_PREFIX + message.summary + BRANCH_SUMMARY_SUFFIX
                        ),
                    ),
                    timestamp=message.timestamp,
                )
            )
        else:
            converted.append(
                UserMessage(
                    content=(
                        TextContent(
                            text=COMPACTION_SUMMARY_PREFIX
                            + message.summary
                            + COMPACTION_SUMMARY_SUFFIX
                        ),
                    ),
                    timestamp=message.timestamp,
                )
            )
    return tuple(converted)


__all__ = [
    "AgentMessage",
    "BRANCH_SUMMARY_PREFIX",
    "BRANCH_SUMMARY_SUFFIX",
    "BashExecutionMessage",
    "BranchSummaryMessage",
    "COMPACTION_SUMMARY_PREFIX",
    "COMPACTION_SUMMARY_SUFFIX",
    "CompactionSummaryMessage",
    "CustomMessage",
    "bash_execution_to_text",
    "default_convert_to_llm",
]
