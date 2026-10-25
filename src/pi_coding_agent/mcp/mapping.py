"""Bidirectional mapping between MCP entities and product descriptors (P18-T03)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import cast

from pydantic import BaseModel, Field, create_model

from pi_agent import AgentTool, AgentToolResult
from pi_ai import TextContent

from .contracts import McpTransportError

_JSON_TYPES: dict[str, type[object] | tuple[type[object], ...]] = {
    "string": str,
    "number": float,
    "integer": int,
    "boolean": bool,
    "array": list,
    "object": dict,
    "null": type(None),
}

Relay = Callable[[str, dict[str, object]], Awaitable[dict[str, object]]]


def _model_from_schema(tool_name: str, schema: object) -> type[BaseModel]:
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise ValueError(f"tool {tool_name!r} inputSchema must be an object schema")
    properties = schema.get("properties")
    fields: dict[str, tuple[type[object], object]] = {}
    if isinstance(properties, dict):
        required_raw = schema.get("required")
        required = {name for name in cast("list[object]", required_raw or [])}
        for raw_name, raw_field in cast("dict[str, object]", properties).items():
            name = str(raw_name)
            spec = raw_field if isinstance(raw_field, dict) else {}
            py_type: type[object] | tuple[type[object], ...]
            raw_type = spec.get("type", "object")
            if isinstance(raw_type, list):
                py_type = tuple(_JSON_TYPES.get(str(item), object) for item in raw_type)
            else:
                py_type = _JSON_TYPES.get(str(raw_type), object)
            description = spec.get("description")
            field_desc = str(description) if description is not None else None
            if name in required:
                fields[name] = (py_type, Field(..., description=field_desc))
            else:
                fields[name] = (py_type, Field(default=None, description=field_desc))
    model_name = f"mcp_{tool_name}_args"
    if not fields:
        return create_model(model_name)
    return cast(
        "type[BaseModel]",
        create_model(model_name, **fields),  # type: ignore[call-overload]
    )


def _content_from_result(result: dict[str, object]) -> tuple[TextContent, ...]:
    blocks: list[TextContent] = []
    raw = result.get("content")
    if isinstance(raw, list):
        for block in cast("list[object]", raw):
            if isinstance(block, dict) and block.get("type") == "text":
                blocks.append(TextContent(text=str(block.get("text", ""))))
    return tuple(blocks)


@dataclass(frozen=True, slots=True)
class McpPromptDescriptor:
    name: str
    description: str
    source: str
    arguments: tuple[dict[str, object], ...]


class McpToolCallError(RuntimeError):
    """The MCP tool reported a tool-level error (isError=true)."""


def _text_from_result(result: dict[str, object]) -> str:
    blocks = result.get("content")
    if isinstance(blocks, list):
        texts = [
            str(block.get("text", ""))
            for block in cast("list[object]", blocks)
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "\n".join(text for text in texts if text)
    return ""


def map_tools(
    entries: list[dict[str, object]],
    *,
    server: str,
    relay: Relay,
) -> tuple[AgentTool[BaseModel, object], ...]:
    """Convert MCP tools/list entries into AgentTools that relay execution."""

    tools: list[AgentTool[BaseModel, object]] = []
    for entry in entries:
        name = str(entry.get("name", ""))
        if not name:
            continue
        parameter_type = _model_from_schema(name, entry.get("inputSchema"))

        async def execute(
            _call_id: str,
            params: BaseModel,
            _abort: object,
            _update: object,
            *,
            _tool_name: str = name,
        ) -> AgentToolResult[object]:
            try:
                result = await relay(_tool_name, params.model_dump(mode="json", exclude_none=True))
            except McpTransportError as error:
                raise McpToolCallError(str(error)) from error
            if result.get("isError"):
                raise McpToolCallError(_text_from_result(result))
            return AgentToolResult[object](
                content=_content_from_result(result),
                details=None,
            )

        tools.append(
            AgentTool(
                name=name,
                label=str(entry.get("name", name)),
                description=str(entry.get("description", "")),
                parameter_type=parameter_type,
                execute=execute,
            )
        )
    return tuple(tools)


def map_prompts(
    entries: list[dict[str, object]], *, server: str
) -> tuple[McpPromptDescriptor, ...]:
    """Convert MCP prompts/list entries into product prompt descriptors."""

    return tuple(
        McpPromptDescriptor(
            name=str(entry.get("name", "")),
            description=str(entry.get("description", "")),
            source=f"mcp:{server}",
            arguments=tuple(
                cast("dict[str, object]", argument)
                for argument in cast("list[object]", entry.get("arguments") or [])
                if isinstance(argument, dict)
            ),
        )
        for entry in entries
        if entry.get("name")
    )


__all__ = ["McpPromptDescriptor", "McpToolCallError", "map_prompts", "map_tools"]
