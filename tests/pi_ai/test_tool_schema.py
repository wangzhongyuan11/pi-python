from __future__ import annotations

from typing import Literal, cast

import pytest
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pi_ai.context import Context
from pi_ai.messages import JsonObject, ToolCall
from pi_ai.tools import Tool, UnknownToolError, validate_tool_arguments, validate_tool_call
from pi_ai.wire.tools import dump_tool


class ReadParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    path: str = Field(description="File to read")
    offset: int = Field(default=1, ge=1)
    mode: Literal["text", "binary"] = "text"


def _read_tool() -> Tool[ReadParameters]:
    return Tool(
        name="read",
        description="Read a file",
        parameter_type=ReadParameters,
    )


def test_tool_exposes_a_detached_provider_json_schema() -> None:
    tool = _read_tool()
    context = Context(messages=(), tools=(tool,))

    first = tool.parameters
    second = tool.parameters

    assert first == second
    assert context.tools == (tool,)
    assert first is not second
    assert first["type"] == "object"
    assert first["required"] == ["path"]
    assert first["additionalProperties"] is False
    properties = cast("JsonObject", first["properties"])
    path_schema = cast("JsonObject", properties["path"])
    assert path_schema["description"] == "File to read"
    assert dump_tool(tool) == {
        "name": "read",
        "description": "Read a file",
        "parameters": first,
    }

    first["title"] = "mutated"
    assert "title" not in tool.parameters or tool.parameters["title"] != "mutated"


def test_tool_arguments_validate_strictly_without_mutating_input() -> None:
    tool = _read_tool()
    arguments: JsonObject = {"path": "README.md", "offset": 2, "mode": "binary"}
    call = ToolCall(id="call-1", name="read", arguments=arguments.copy())

    validated = validate_tool_arguments(tool, call)

    assert validated == ReadParameters(path="README.md", offset=2, mode="binary")
    assert arguments == {"path": "README.md", "offset": 2, "mode": "binary"}


INVALID_ARGUMENTS: tuple[JsonObject, ...] = (
    {},
    {"path": 7},
    {"path": "README.md", "offset": 0},
    {"path": "README.md", "offset": "2"},
    {"path": "README.md", "unexpected": True},
)


@pytest.mark.parametrize("arguments", INVALID_ARGUMENTS)
def test_tool_argument_failure_matrix(arguments: JsonObject) -> None:
    call = ToolCall(id="call-1", name="read", arguments=arguments)

    with pytest.raises(ValidationError):
        validate_tool_arguments(_read_tool(), call)


def test_tool_lookup_is_explicit_and_unknown_tools_are_typed() -> None:
    call = ToolCall(id="call-1", name="missing", arguments={})

    with pytest.raises(UnknownToolError, match='Tool "missing" not found'):
        validate_tool_call([_read_tool()], call)


def test_tool_parameter_root_must_be_a_json_object() -> None:
    with pytest.raises(ValueError, match="object-rooted"):
        Tool(name="invalid", description="invalid", parameter_type=list[str])
