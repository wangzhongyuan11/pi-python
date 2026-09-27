"""Node extension host wire protocol (P15.5-T01).

Python and the Node extension host negotiate a single protocol version over
JSONL stdio. The handshake exchanges versions, the host generation, and the
capability list; every later frame is a correlated request/response pair in
either direction. Unknown commands and unknown capabilities fail with typed
error codes instead of being ignored.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError

PROTOCOL_VERSION = 1

CAPABILITIES: frozenset[str] = frozenset(
    {
        "register_tool",
        "register_command",
        "register_flag",
        "register_shortcut",
        "register_message_renderer",
        "register_entry_renderer",
        "events",
        "actions",
        "ui",
        "exec",
    }
)

FRAME_TYPES: frozenset[str] = frozenset({"hello", "hello_ack", "request", "response"})


class ProtocolError(ValueError):
    """A wire frame or negotiated capability failed validation."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


class Hello(BaseModel):
    """Python → Node handshake offering the protocol version it speaks.

    The state snapshot lets the host answer synchronous reads (flags, active
    tools, session name, thinking level) without a round trip, matching the
    upstream synchronous ExtensionAPI semantics.
    """

    type: Literal["hello"] = "hello"
    protocol: int = PROTOCOL_VERSION
    generation: int = 0
    cwd: str = ""
    state: dict[str, object] = Field(default_factory=dict)


class HelloAck(BaseModel):
    """Node → Python handshake reply with the negotiated capabilities."""

    model_config = ConfigDict(populate_by_name=True)

    type: Literal["hello_ack"] = "hello_ack"
    protocol: int = PROTOCOL_VERSION
    host: str = "node"
    generation: int = 0
    capabilities: tuple[str, ...] = ()
    extensions: tuple[dict[str, object], ...] = ()


class Request(BaseModel):
    """A correlated request frame, valid in both directions."""

    type: Literal["request"] = "request"
    id: str
    command: str
    payload: dict[str, object] = Field(default_factory=dict)


class Response(BaseModel):
    """The correlated reply to a Request frame."""

    model_config = ConfigDict(populate_by_name=True)

    type: Literal["response"] = "response"
    id: str
    ok: bool = True
    result: object = None
    error_code: str | None = Field(default=None, alias="errorCode")
    error: str | None = None


HostFrame = HelloAck | Response
PythonFrame = Hello | Request


def negotiate(hello: Hello, host_protocol: int, host_capabilities: Sequence[str]) -> HelloAck:
    """Validate the offered protocol version against the host and reply."""

    if hello.protocol != PROTOCOL_VERSION:
        raise ProtocolError(
            "version_mismatch",
            f"python speaks protocol {PROTOCOL_VERSION}, host speaks {host_protocol}",
        )
    unknown = sorted(name for name in host_capabilities if name not in CAPABILITIES)
    if unknown:
        raise ProtocolError(
            "unknown_capability",
            f"host reported unknown capabilities: {', '.join(unknown)}",
        )
    return HelloAck(
        protocol=host_protocol,
        generation=hello.generation,
        capabilities=tuple(host_capabilities),
    )


def parse_frame(line: str) -> Hello | HelloAck | Request | Response:
    """Parse one JSONL frame or raise a typed invalid_frame error."""

    try:
        raw_payload: object = json.loads(line)
    except json.JSONDecodeError as error:
        raise ProtocolError("invalid_frame", f"not JSON: {error}") from error
    payload = cast("dict[str, object]", raw_payload) if isinstance(raw_payload, dict) else {}
    raw_kind = payload.get("type")
    kind = raw_kind if isinstance(raw_kind, str) else ""
    if kind not in FRAME_TYPES:
        raise ProtocolError("invalid_frame", f"unknown frame type in {line[:80]!r}")
    models: dict[str, type[Hello | HelloAck | Request | Response]] = {
        "hello": Hello,
        "hello_ack": HelloAck,
        "request": Request,
        "response": Response,
    }
    model = models[kind]
    try:
        return model.model_validate(payload)
    except ValidationError as error:
        raise ProtocolError("invalid_frame", str(error)) from error


__all__ = [
    "CAPABILITIES",
    "FRAME_TYPES",
    "PROTOCOL_VERSION",
    "Hello",
    "HelloAck",
    "HostFrame",
    "ProtocolError",
    "PythonFrame",
    "Request",
    "Response",
    "negotiate",
    "parse_frame",
]
