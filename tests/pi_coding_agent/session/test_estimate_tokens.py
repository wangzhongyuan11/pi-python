"""P15.5/1.1.0 gap closure: compaction estimates 3.5 chars per token.

Upstream found that 4 chars/token under-estimated input size and caused
context-limit request failures; 3.5 reduces them.
"""

from __future__ import annotations

import math

from pi_ai import UserMessage
from pi_ai.wire.messages import dump_message
from pi_coding_agent.compaction.cutpoint import estimate_entry_tokens
from pi_coding_agent.session.models import MessageEntry


def _entry(text: str) -> MessageEntry:
    return MessageEntry(
        type="message",
        id="e1",
        parent_id=None,
        timestamp="2026-09-28T00:00:00.000Z",
        message=dump_message(UserMessage(content=text, timestamp=0)),
    )


def test_estimate_uses_three_point_five_chars_per_token() -> None:
    entry = _entry("x" * 350)

    # 3.5 chars/token → exactly 100 tokens for 350 chars (ceil handles json overhead).
    tokens = estimate_entry_tokens(entry)

    expected = math.ceil((len(entry.model_dump_json(by_alias=True, exclude_none=True)) / 3.5))
    assert tokens == expected
    assert tokens > 0


def test_estimate_never_undercounts_vs_four_chars() -> None:
    entry = _entry("y" * 700)
    tokens = estimate_entry_tokens(entry)
    four_chars = math.ceil(len(entry.model_dump_json(by_alias=True, exclude_none=True)) / 4)
    assert tokens >= four_chars
