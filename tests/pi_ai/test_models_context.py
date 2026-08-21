from __future__ import annotations

from typing import cast

import pytest
from pydantic import ValidationError

from pi_ai.context import Context
from pi_ai.messages import AssistantMessage, TextContent, ToolResultMessage, UserMessage
from pi_ai.models import (
    Model,
    ModelCost,
    ModelCostTier,
    clamp_thinking_level,
    get_supported_thinking_levels,
)
from pi_ai.usage import Usage, UsageCost, validate_thinking_level
from pi_ai.wire.messages import dump_message, parse_message


def _usage(**changes: int) -> Usage:
    values = {
        "input": 10,
        "output": 5,
        "cache_read": 2,
        "cache_write": 1,
        "total_tokens": 18,
    }
    values.update(changes)
    return Usage(
        cost=UsageCost(input=0.1, output=0.2, cache_read=0.0, cache_write=0.0, total=0.3), **values
    )


def test_usage_is_a_validated_message_atom_and_round_trips_aliases() -> None:
    usage = _usage(reasoning=3, cache_write_1h=1)
    assistant = AssistantMessage(
        content=(TextContent(text="done"),),
        api="openai-completions",
        provider="deepseek",
        model="deepseek-chat",
        usage=usage,
        stop_reason="stop",
        timestamp=1,
    )
    tool_result = ToolResultMessage(
        tool_call_id="call-1",
        tool_name="read",
        content=(TextContent(text="data"),),
        usage=usage,
        is_error=False,
        timestamp=2,
    )

    assistant_wire = dump_message(assistant)
    tool_wire = dump_message(tool_result)

    assert assistant_wire["usage"] == {
        "input": 10,
        "output": 5,
        "cacheRead": 2,
        "cacheWrite": 1,
        "cacheWrite1h": 1,
        "reasoning": 3,
        "totalTokens": 18,
        "cost": {
            "input": 0.1,
            "output": 0.2,
            "cacheRead": 0.0,
            "cacheWrite": 0.0,
            "total": 0.3,
        },
    }
    assert parse_message(assistant_wire) == assistant
    assert parse_message(tool_wire) == tool_result


@pytest.mark.parametrize(
    "usage",
    [
        lambda: _usage(input=-1),
        lambda: _usage(output=2, reasoning=3),
        lambda: _usage(cache_write=1, cache_write_1h=2),
    ],
)
def test_usage_rejects_negative_counts_and_invalid_subsets(usage: object) -> None:
    with pytest.raises(ValueError):
        assert callable(usage)
        usage()


def test_usage_wire_rejects_coercion_and_missing_cost_fields() -> None:
    payload = cast(
        object,
        {
            "role": "assistant",
            "content": [],
            "api": "test",
            "provider": "test",
            "model": "test",
            "usage": {
                "input": "1",
                "output": 0,
                "cacheRead": 0,
                "cacheWrite": 0,
                "totalTokens": 1,
                "cost": {},
            },
            "stopReason": "stop",
            "timestamp": 1,
        },
    )

    with pytest.raises(ValidationError):
        parse_message(payload)


def test_model_and_thinking_level_invariants() -> None:
    model = Model(
        id="deepseek-chat",
        name="DeepSeek Pro",
        api="openai-completions",
        provider="deepseek",
        base_url="https://api.deepseek.com",
        reasoning=True,
        thinking_level_map={"xhigh": None, "max": "max"},
        input=("text",),
        cost=ModelCost(input=0.1, output=0.2, cache_read=0.01, cache_write=0.1),
        context_window=128_000,
        max_tokens=8_192,
    )

    assert validate_thinking_level("minimal") == "minimal"
    with pytest.raises(ValidationError):
        validate_thinking_level("extreme")
    assert get_supported_thinking_levels(model) == (
        "off",
        "minimal",
        "low",
        "medium",
        "high",
        "max",
    )
    assert clamp_thinking_level(model, "xhigh") == "max"

    with pytest.raises(ValueError, match="context_window"):
        Model(
            id="broken",
            name="Broken",
            api="test",
            provider="test",
            base_url="https://example.invalid",
            reasoning=False,
            input=("text",),
            cost=ModelCost(input=0, output=0, cache_read=0, cache_write=0),
            context_window=0,
            max_tokens=1,
        )


def test_model_cost_tier_runs_base_rate_validation() -> None:
    tier = ModelCostTier(
        input=0.1,
        output=0.2,
        cache_read=0.01,
        cache_write=0.1,
        input_tokens_above=100_000,
    )

    assert tier.input_tokens_above == 100_000
    with pytest.raises(ValueError, match="finite and non-negative"):
        ModelCostTier(
            input=-0.1,
            output=0.2,
            cache_read=0.01,
            cache_write=0.1,
            input_tokens_above=100_000,
        )


def test_context_captures_an_immutable_message_snapshot() -> None:
    source = [UserMessage(content="hello", timestamp=1)]
    context = Context(messages=source, system_prompt="system")
    source.append(UserMessage(content="later", timestamp=2))

    assert context.messages == (UserMessage(content="hello", timestamp=1),)
    assert context.system_prompt == "system"
    assert context.tools is None
