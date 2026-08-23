"""Two-stage conversion from agent transcripts to provider context."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from pi_ai import Context, Message

from .messages import AgentMessage, default_convert_to_llm
from .tools import AgentTool

type TransformContext = Callable[
    [Sequence[AgentMessage]],
    Sequence[AgentMessage] | Awaitable[Sequence[AgentMessage]],
]
type ConvertToLlm = Callable[
    [Sequence[AgentMessage]],
    Sequence[Message] | Awaitable[Sequence[Message]],
]


@dataclass(frozen=True, slots=True, init=False)
class AgentContext:
    system_prompt: str
    messages: tuple[AgentMessage, ...]
    tools: tuple[AgentTool[Any, Any], ...] | None

    def __init__(
        self,
        *,
        system_prompt: str,
        messages: Iterable[AgentMessage],
        tools: Iterable[AgentTool[Any, Any]] | None = None,
    ) -> None:
        object.__setattr__(self, "system_prompt", system_prompt)
        object.__setattr__(self, "messages", tuple(messages))
        object.__setattr__(self, "tools", None if tools is None else tuple(tools))


async def build_llm_context(
    context: AgentContext,
    *,
    transform_context: TransformContext | None = None,
    convert_to_llm: ConvertToLlm = default_convert_to_llm,
) -> Context:
    transformed: Sequence[AgentMessage] = context.messages
    if transform_context is not None:
        transform_result = transform_context(context.messages)
        transformed = (
            await transform_result if inspect.isawaitable(transform_result) else transform_result
        )

    convert_result = convert_to_llm(tuple(transformed))
    converted = await convert_result if inspect.isawaitable(convert_result) else convert_result
    return Context(
        system_prompt=context.system_prompt,
        messages=converted,
        tools=context.tools,
    )


__all__ = [
    "AgentContext",
    "ConvertToLlm",
    "TransformContext",
    "build_llm_context",
]
