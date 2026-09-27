"""Node extension host protocol contract tests (P15.5-T01)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pi_coding_agent.node_host.models import (
    CAPABILITIES,
    PROTOCOL_VERSION,
    Hello,
    HelloAck,
    ProtocolError,
    Request,
    Response,
    negotiate,
    parse_frame,
)


def test_hello_and_ack_round_trip_with_capabilities() -> None:
    hello = Hello(cwd="/project", generation=3)
    ack = negotiate(hello, PROTOCOL_VERSION, ["register_tool", "events", "ui"])

    assert ack.type == "hello_ack"
    assert ack.protocol == PROTOCOL_VERSION
    assert ack.generation == 3
    assert ack.capabilities == ("register_tool", "events", "ui")
    # The ack round-trips through JSONL framing.
    reparsed = parse_frame(ack.model_dump_json())
    assert reparsed == ack


def test_handshake_rejects_a_version_mismatch() -> None:
    with pytest.raises(ProtocolError) as excinfo:
        negotiate(Hello(protocol=PROTOCOL_VERSION + 1), PROTOCOL_VERSION, ["events"])
    assert excinfo.value.code == "version_mismatch"


def test_handshake_rejects_unknown_capabilities() -> None:
    with pytest.raises(ProtocolError) as excinfo:
        negotiate(Hello(), PROTOCOL_VERSION, ["events", "make_coffee"])
    assert excinfo.value.code == "unknown_capability"
    assert "make_coffee" in str(excinfo.value)


def test_frames_parse_from_jsonl_lines_and_fail_typed() -> None:
    request = parse_frame('{"type":"request","id":"r1","command":"register_tool"}')
    assert isinstance(request, Request)
    assert request.command == "register_tool"

    response = parse_frame('{"type":"response","id":"r1","ok":false,"errorCode":"handler_error"}')
    assert isinstance(response, Response)
    assert response.error_code == "handler_error"
    assert response.ok is False

    with pytest.raises(ProtocolError) as excinfo:
        parse_frame("not json")
    assert excinfo.value.code == "invalid_frame"
    with pytest.raises(ProtocolError) as excinfo:
        parse_frame('{"type":"mystery"}')
    assert excinfo.value.code == "invalid_frame"
    with pytest.raises(ProtocolError):
        parse_frame('{"type":"request","command":"missing-id"}')


def test_protocol_version_is_frozen_by_test() -> None:
    # The wire contract is versioned; bumping it must be a deliberate change
    # coordinated with node/extension-host/src/protocol.ts.
    assert PROTOCOL_VERSION == 1
    assert "register_tool" in CAPABILITIES
    assert "events" in CAPABILITIES
    with pytest.raises(ValidationError):
        Hello(type="not-hello")  # type: ignore[arg-type]
