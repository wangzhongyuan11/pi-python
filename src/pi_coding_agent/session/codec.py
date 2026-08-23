"""Validation and serialization for individual Session v3 JSONL records."""

from __future__ import annotations

from typing import cast

from pydantic import TypeAdapter

from pi_ai import JsonValue

from .models import SessionRecord

_RECORD_ADAPTER = TypeAdapter[SessionRecord](SessionRecord)


def parse_record(payload: object) -> SessionRecord:
    """Validate one decoded JSON value as a known Session v3 record."""

    return _RECORD_ADAPTER.validate_python(payload)


def dump_record(record: SessionRecord) -> dict[str, JsonValue]:
    """Serialize a record with the upstream-compatible camelCase field names."""

    return cast(
        "dict[str, JsonValue]",
        record.model_dump(mode="json", by_alias=True, exclude_none=True),
    )


__all__ = ["dump_record", "parse_record"]
