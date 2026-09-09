"""Strict wire models shared by the local RPC server and clients."""

from __future__ import annotations

from typing import Any, ClassVar, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

RpcCommandType = Literal[
    "prompt",
    "steer",
    "follow_up",
    "abort",
    "new_session",
    "get_state",
    "set_model",
    "cycle_model",
    "get_available_models",
    "set_thinking_level",
    "cycle_thinking_level",
    "get_available_thinking_levels",
    "set_steering_mode",
    "set_follow_up_mode",
    "compact",
    "set_auto_compaction",
    "set_auto_retry",
    "abort_retry",
    "bash",
    "abort_bash",
    "get_session_stats",
    "export_html",
    "switch_session",
    "fork",
    "clone",
    "get_fork_messages",
    "get_entries",
    "get_tree",
    "get_last_assistant_text",
    "set_session_name",
    "get_messages",
    "get_commands",
]


class _WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)


class RpcCommand(_WireModel):
    """Validated union-shaped command matching upstream's discriminated wire surface."""

    id: str | None = None
    type: RpcCommandType
    message: str | None = None
    images: list[dict[str, Any]] | None = None
    streaming_behavior: Literal["steer", "followUp"] | None = Field(
        default=None, alias="streamingBehavior"
    )
    parent_session: str | None = Field(default=None, alias="parentSession")
    provider: str | None = None
    model_id: str | None = Field(default=None, alias="modelId")
    level: Literal["off", "minimal", "low", "medium", "high", "xhigh", "max"] | None = None
    mode: Literal["all", "one-at-a-time"] | None = None
    custom_instructions: str | None = Field(default=None, alias="customInstructions")
    enabled: bool | None = None
    command: str | None = None
    exclude_from_context: bool | None = Field(default=None, alias="excludeFromContext")
    output_path: str | None = Field(default=None, alias="outputPath")
    session_path: str | None = Field(default=None, alias="sessionPath")
    entry_id: str | None = Field(default=None, alias="entryId")
    since: str | None = None
    name: str | None = None

    _required: ClassVar[dict[str, tuple[str, ...]]] = {
        "prompt": ("message",),
        "steer": ("message",),
        "follow_up": ("message",),
        "set_model": ("provider", "model_id"),
        "set_thinking_level": ("level",),
        "set_steering_mode": ("mode",),
        "set_follow_up_mode": ("mode",),
        "set_auto_compaction": ("enabled",),
        "set_auto_retry": ("enabled",),
        "bash": ("command",),
        "switch_session": ("session_path",),
        "fork": ("entry_id",),
        "set_session_name": ("name",),
    }

    @model_validator(mode="after")
    def _require_command_fields(self) -> Self:
        missing = [
            name for name in self._required.get(self.type, ()) if getattr(self, name) is None
        ]
        if missing:
            raise ValueError(f"{self.type} requires {', '.join(missing)}")
        return self


class RpcResponse(_WireModel):
    id: str | None = None
    type: Literal["response"] = "response"
    command: str
    success: bool
    data: Any | None = None
    error: str | None = None

    @model_validator(mode="after")
    def _validate_shape(self) -> Self:
        if self.success and self.error is not None:
            raise ValueError("successful response cannot contain error")
        if not self.success and self.error is None:
            raise ValueError("failed response requires error")
        return self


class RpcSessionState(_WireModel):
    model: dict[str, Any] | None = None
    thinking_level: str = Field(alias="thinkingLevel")
    is_streaming: bool = Field(alias="isStreaming")
    is_compacting: bool = Field(alias="isCompacting")
    steering_mode: Literal["all", "one-at-a-time"] = Field(alias="steeringMode")
    follow_up_mode: Literal["all", "one-at-a-time"] = Field(alias="followUpMode")
    session_file: str | None = Field(default=None, alias="sessionFile")
    session_id: str = Field(alias="sessionId")
    session_name: str | None = Field(default=None, alias="sessionName")
    auto_compaction_enabled: bool = Field(alias="autoCompactionEnabled")
    message_count: int = Field(alias="messageCount")
    pending_message_count: int = Field(alias="pendingMessageCount")


class RpcEvent(BaseModel):
    """Agent event frame; event-specific fields stay lossless for clients."""

    model_config = ConfigDict(extra="allow", strict=True)
    type: str


_COMMAND_ADAPTER = TypeAdapter(RpcCommand)


def parse_rpc_command(value: object) -> RpcCommand:
    return _COMMAND_ADAPTER.validate_python(value)


__all__ = [
    "RpcCommand",
    "RpcCommandType",
    "RpcEvent",
    "RpcResponse",
    "RpcSessionState",
    "parse_rpc_command",
]
