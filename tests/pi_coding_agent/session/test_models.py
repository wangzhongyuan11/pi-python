from __future__ import annotations

import pytest
from pydantic import ValidationError

from pi_coding_agent.session.codec import dump_record, parse_record
from pi_coding_agent.session.models import SessionEntry, SessionHeader

HEADER = {
    "type": "session",
    "version": 3,
    "id": "session-1",
    "timestamp": "2026-08-24T00:00:00.000Z",
    "cwd": "D:\\work",
}


@pytest.mark.parametrize(
    "entry",
    [
        {"type": "message", "message": {"role": "user", "content": "hi", "timestamp": 1}},
        {"type": "thinking_level_change", "thinkingLevel": "high"},
        {"type": "model_change", "provider": "deepseek", "modelId": "deepseek-chat"},
        {
            "type": "compaction",
            "summary": "summary",
            "firstKeptEntryId": "e1",
            "tokensBefore": 42,
            "details": {"source": "test"},
        },
        {"type": "branch_summary", "fromId": "e1", "summary": "branch"},
        {"type": "custom", "customType": "counter", "data": {"value": 1}},
        {
            "type": "custom_message",
            "customType": "notice",
            "content": [{"type": "text", "text": "hello"}],
            "display": True,
        },
        {"type": "label", "targetId": "e1", "label": "important"},
        {"type": "session_info", "name": "demo"},
    ],
)
def test_all_entry_types_round_trip_with_camel_case(entry: dict[str, object]) -> None:
    payload = {
        "id": "e2",
        "parentId": "e1",
        "timestamp": "2026-08-24T00:00:01.000Z",
        **entry,
        "futureField": {"preserved": True},
    }

    parsed = parse_record(payload)

    assert isinstance(parsed, SessionEntry)
    assert dump_record(parsed) == payload


def test_header_is_the_only_record_with_version() -> None:
    parsed = parse_record(HEADER)

    assert isinstance(parsed, SessionHeader)
    assert dump_record(parsed) == HEADER


def test_unknown_entry_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        parse_record(
            {
                "type": "future_entry",
                "id": "e1",
                "parentId": None,
                "timestamp": "2026-08-24T00:00:01.000Z",
            }
        )
