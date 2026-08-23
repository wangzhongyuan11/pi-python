"""Session identifier validation shared by create, open, fork, and import."""

from __future__ import annotations

import re

from .errors import InvalidSessionIdError

_VALID_ID = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")


def validate_session_id(value: str) -> str:
    if _VALID_ID.fullmatch(value) is None:
        raise InvalidSessionIdError(f"invalid session id: {value!r}")
    return value


__all__ = ["validate_session_id"]
