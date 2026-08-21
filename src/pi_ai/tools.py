"""Provider tool definitions backed by strict Pydantic parameter validation."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from copy import deepcopy
from typing import cast

from pydantic import TypeAdapter

from .messages import JsonObject, ToolCall


class UnknownToolError(LookupError):
    """Raised when a model calls a tool absent from the request context."""


class Tool[ParamsT]:
    """A provider-visible tool schema paired with its Python validator."""

    __slots__ = ("_parameters", "_validate", "description", "name")

    def __init__(
        self,
        *,
        name: str,
        description: str,
        parameter_type: type[ParamsT],
    ) -> None:
        if not name:
            raise ValueError("tool name must not be empty")
        if not description:
            raise ValueError("tool description must not be empty")
        adapter = TypeAdapter[ParamsT](parameter_type)
        parameters = cast("JsonObject", adapter.json_schema(mode="validation", by_alias=True))
        if parameters.get("type") != "object":
            raise ValueError("tool parameters must have an object-rooted JSON schema")
        self.name = name
        self.description = description
        self._parameters = deepcopy(parameters)

        def validate(arguments: object) -> ParamsT:
            return adapter.validate_python(deepcopy(arguments), strict=True)

        self._validate: Callable[[object], ParamsT] = validate

    @property
    def parameters(self) -> JsonObject:
        return deepcopy(self._parameters)

    def validate_arguments(self, arguments: object) -> ParamsT:
        return self._validate(arguments)


def validate_tool_arguments[ParamsT](tool: Tool[ParamsT], tool_call: ToolCall) -> ParamsT:
    return tool.validate_arguments(tool_call.arguments)


def validate_tool_call[ParamsT](
    tools: Iterable[Tool[ParamsT]],
    tool_call: ToolCall,
) -> ParamsT:
    tool = next((candidate for candidate in tools if candidate.name == tool_call.name), None)
    if tool is None:
        raise UnknownToolError(f'Tool "{tool_call.name}" not found')
    return validate_tool_arguments(tool, tool_call)


__all__ = [
    "Tool",
    "UnknownToolError",
    "validate_tool_arguments",
    "validate_tool_call",
]
