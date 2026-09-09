from __future__ import annotations

import pytest
from pydantic import ValidationError

from pi_coding_agent.rpc.models import (
    RpcResponse,
    RpcSessionState,
    parse_rpc_command,
)


def test_prompt_command_accepts_wire_aliases_and_preserves_request_id() -> None:
    command = parse_rpc_command(
        {
            "id": "request-7",
            "type": "prompt",
            "message": "hello",
            "streamingBehavior": "followUp",
        }
    )

    assert command.id == "request-7"
    assert command.streaming_behavior == "followUp"
    assert command.model_dump(by_alias=True, exclude_none=True) == {
        "id": "request-7",
        "type": "prompt",
        "message": "hello",
        "streamingBehavior": "followUp",
    }


def test_command_rejects_unknown_type_and_missing_required_payload() -> None:
    with pytest.raises(ValidationError):
        parse_rpc_command({"id": "bad", "type": "unknown"})
    with pytest.raises(ValidationError):
        parse_rpc_command({"type": "set_model", "provider": "deepseek"})


def test_response_enforces_success_and_failure_shapes() -> None:
    response = RpcResponse(command="abort", success=True, id="a")
    assert response.model_dump(by_alias=True, exclude_none=True) == {
        "id": "a",
        "type": "response",
        "command": "abort",
        "success": True,
    }

    with pytest.raises(ValidationError):
        RpcResponse(command="abort", success=False)
    with pytest.raises(ValidationError):
        RpcResponse(command="abort", success=True, error="no")


def test_state_uses_upstream_camel_case_wire_names() -> None:
    state = RpcSessionState.model_validate(
        {
            "thinkingLevel": "high",
            "isStreaming": False,
            "isCompacting": False,
            "steeringMode": "all",
            "followUpMode": "one-at-a-time",
            "sessionId": "s1",
            "autoCompactionEnabled": True,
            "messageCount": 3,
            "pendingMessageCount": 1,
        }
    )

    assert state.session_id == "s1"
    assert state.model_dump(by_alias=True)["followUpMode"] == "one-at-a-time"
