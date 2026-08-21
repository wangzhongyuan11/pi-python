"""Strict provider wire encoding for tool definitions."""

from __future__ import annotations

from typing import cast

from pydantic import BaseModel, ConfigDict

from ..messages import JsonObject, JsonValue
from ..tools import Tool


class ToolWire(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str
    description: str
    parameters: JsonObject


def dump_tool[ParamsT](tool: Tool[ParamsT]) -> dict[str, JsonValue]:
    wire = ToolWire(
        name=tool.name,
        description=tool.description,
        parameters=tool.parameters,
    )
    return cast("dict[str, JsonValue]", wire.model_dump(mode="json"))


__all__ = ["ToolWire", "dump_tool"]
