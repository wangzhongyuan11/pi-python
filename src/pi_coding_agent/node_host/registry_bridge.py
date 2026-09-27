"""Bidirectional registry proxies for the Node extension host (P15.5-T03).

Registrations announced by the host are materialized inside the Python
capability registry so every product surface (Agent tools, TUI commands and
shortcuts, CLI flags) sees them natively. Tool and command functions stay in
Node; the Python side holds proxies that call back over the wire.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any, cast

from pydantic import BaseModel, Field, create_model

from pi_agent import AgentTool, AgentToolResult
from pi_ai import TextContent
from pi_coding_agent.extensions.registry import FlagState

HostCaller = Callable[[str, Mapping[str, object]], Awaitable[object]]

_JSON_SCHEMA_TYPES: dict[str, type[Any] | tuple[type[Any], ...]] = {
    "string": str,
    "number": float,
    "integer": int,
    "boolean": bool,
    "array": list,
    "object": dict,
    "null": type(None),
}


def model_from_json_schema(name: str, schema: Mapping[str, object]) -> type[BaseModel]:
    """Build a shallow pydantic model from a TypeBox/JSON schema object."""

    properties_raw = schema.get("properties")
    fields: dict[str, tuple[type[Any], object]] = {}
    if isinstance(properties_raw, Mapping):
        properties = cast("Mapping[str, object]", properties_raw)
        required_raw = schema.get("required")
        required_list = cast("list[object]", required_raw) if isinstance(required_raw, list) else []
        required_names = {item for item in required_list if isinstance(item, str)}
        for raw_name, raw_field in properties.items():
            field_name = str(raw_name)
            if not isinstance(raw_field, Mapping):
                fields[field_name] = (object, None)
                continue
            field = cast("Mapping[str, object]", raw_field)
            raw_type = field.get("type", "object")
            python_type: Any
            if isinstance(raw_type, list):
                type_names = cast("list[object]", raw_type)
                options = tuple(_JSON_SCHEMA_TYPES.get(str(item), object) for item in type_names)
                python_type = options or object
            else:
                python_type = _JSON_SCHEMA_TYPES.get(str(raw_type), object)
            raw_description = field.get("description")
            description = str(raw_description) if raw_description is not None else None
            if field_name in required_names:
                fields[field_name] = (
                    python_type,
                    Field(..., description=description),
                )
            else:
                fields[field_name] = (
                    python_type,
                    Field(default=None, description=description),
                )
    model_name = f"{name}Args"
    if not fields:
        return create_model(model_name)
    return cast(
        "type[BaseModel]",
        create_model(model_name, **fields),  # type: ignore[call-overload]
    )


def _as_mapping(value: object) -> Mapping[str, object]:
    return cast("Mapping[str, object]", value if isinstance(value, Mapping) else {})


def _content_from_wire(raw: object) -> tuple[TextContent, ...]:
    blocks: list[TextContent] = []
    if isinstance(raw, list):
        for raw_block in cast("list[object]", raw):
            if not isinstance(raw_block, Mapping):
                continue
            block = cast("Mapping[str, object]", raw_block)
            if block.get("type") == "text":
                blocks.append(TextContent(text=str(block.get("text", ""))))
    return tuple(blocks)


class RegistryBridge:
    """Answer host registration requests and expose reverse proxies."""

    def __init__(
        self,
        registry: object,
        *,
        source: str,
        host_caller: HostCaller,
    ) -> None:
        self._registry = registry
        self._source = source
        self._host_caller = host_caller

    async def handle_request(self, command: str, payload: Mapping[str, object]) -> object:
        handler = getattr(self, f"_{command}", None)
        if not callable(handler):
            raise NodeRequestError(f"registry bridge cannot handle {command!r}")
        return await cast("Callable[[Mapping[str, object]], Awaitable[object]]", handler)(payload)

    async def _register_tool(self, payload: Mapping[str, object]) -> object:
        raw_definition = payload.get("definition")
        if not isinstance(raw_definition, Mapping):
            raise NodeRequestError("register_tool requires a definition object")
        definition = cast("Mapping[str, object]", raw_definition)
        name = str(definition.get("name", "")).strip()
        if not name:
            raise NodeRequestError("register_tool requires a tool name")
        parameter_type = model_from_json_schema(
            name, cast("Mapping[str, object]", definition.get("parameters") or {})
        )

        async def execute(
            call_id: str, params: BaseModel, _abort: object, _update: object
        ) -> AgentToolResult[object]:
            raw = await self._host_caller(
                "execute_tool",
                {
                    "name": name,
                    "tool_call_id": call_id,
                    "args": params.model_dump(mode="json"),
                },
            )
            result = cast("Mapping[str, object]", raw if isinstance(raw, Mapping) else {})
            return AgentToolResult[object](
                content=_content_from_wire(result.get("content")),
                details=result.get("details"),
            )

        tool: AgentTool[BaseModel, object] = AgentTool(
            name=name,
            label=str(definition.get("label", name)),
            description=str(definition.get("description", "")),
            parameter_type=parameter_type,
            execute=execute,
        )
        self._register("tool", name, tool)
        return {"registered": name}

    async def _register_command(self, payload: Mapping[str, object]) -> object:
        name = str(payload.get("name", "")).strip()
        options = _as_mapping(payload.get("options"))
        description = str(options.get("description", ""))

        async def handler(args: str, context: object) -> object:
            del context
            raw = await self._host_caller(
                "run_command",
                {"name": name, "args": args, "context": {"hasUI": True}},
            )
            result = _as_mapping(raw)
            return result.get("result")

        self._register("command", name, handler)
        return {"registered": name, "description": description}

    async def _register_flag(self, payload: Mapping[str, object]) -> object:
        name = str(payload.get("name", "")).strip()
        options = _as_mapping(payload.get("options"))
        value_type: str = "boolean"
        default: bool | str | None = None
        value_type = str(options.get("type", "boolean"))
        default = cast("bool | str | None", options.get("default"))
        self._register("flag", name, FlagState(value_type=value_type, value=default))  # type: ignore[arg-type]
        return {"registered": name}

    async def _register_shortcut(self, payload: Mapping[str, object]) -> object:
        shortcut = str(payload.get("shortcut", "")).strip()
        options = _as_mapping(payload.get("options"))
        description = str(options.get("description", ""))

        async def handler(context: object) -> object:
            del context
            raw = await self._host_caller(
                "run_shortcut", {"shortcut": shortcut, "context": {"hasUI": True}}
            )
            result = _as_mapping(raw)
            return result.get("result")

        self._register("shortcut", shortcut, handler)
        return {"registered": shortcut, "description": description}

    async def _get_flag(self, payload: Mapping[str, object]) -> object:
        name = str(payload.get("name", ""))
        lookup = cast("object | None", self._registry.lookup("flag", name))
        state = cast("object", getattr(lookup, "payload", None))
        if isinstance(state, FlagState):
            return state.value
        return None

    def _register(self, kind: str, name: str, payload: object) -> object:
        registry = self._registry
        return registry.register(kind, name, self._source, payload)  # type: ignore[union-attr]


class NodeRequestError(RuntimeError):
    """The host requested an operation the bridge cannot perform."""


__all__ = ["NodeRequestError", "RegistryBridge", "model_from_json_schema"]
