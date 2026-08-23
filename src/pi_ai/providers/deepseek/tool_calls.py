"""Stateful assembly of OpenAI-compatible streamed DeepSeek tool calls."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from ...messages import JsonObject, ToolCall


class ToolCallAssemblyError(ValueError):
    """Raised when streamed tool call metadata or arguments are malformed."""


def _field(value: object, name: str) -> object | None:
    if isinstance(value, Mapping):
        return cast("Mapping[object, object]", value).get(name)
    return cast("object | None", getattr(value, name, None))


@dataclass(slots=True)
class StreamingToolCall:
    stream_index: int
    id: str = ""
    name: str = ""
    arguments_json: str = ""

    def consume(self, delta: object) -> str:
        call_id = _field(delta, "id")
        if isinstance(call_id, str) and call_id:
            if self.id and self.id != call_id:
                raise ToolCallAssemblyError("DeepSeek changed a streamed tool call id")
            self.id = call_id

        function = _field(delta, "function")
        name = _field(function, "name")
        if isinstance(name, str) and name:
            self.name += name
        arguments = _field(function, "arguments")
        fragment = arguments if isinstance(arguments, str) else ""
        self.arguments_json += fragment
        return fragment

    def partial(self) -> ToolCall:
        return ToolCall(id=self.id, name=self.name, arguments=self._parse_arguments(strict=False))

    def finalize(self) -> ToolCall:
        if not self.id or not self.name:
            raise ToolCallAssemblyError("DeepSeek returned an incomplete tool call")
        return ToolCall(id=self.id, name=self.name, arguments=self._parse_arguments(strict=True))

    def _parse_arguments(self, *, strict: bool) -> JsonObject:
        try:
            value = cast("object", json.loads(self.arguments_json or "{}"))
        except json.JSONDecodeError:
            if not strict:
                return {}
            raise ToolCallAssemblyError("DeepSeek tool call arguments are not valid JSON") from None
        if not isinstance(value, dict):
            if not strict:
                return {}
            raise ToolCallAssemblyError("DeepSeek tool call arguments must be a JSON object")
        mapping = cast("dict[object, object]", value)
        if any(not isinstance(key, str) for key in mapping):
            if not strict:
                return {}
            raise ToolCallAssemblyError("DeepSeek tool call arguments must be a JSON object")
        return cast("JsonObject", mapping)


class ToolCallAssembler:
    def __init__(self) -> None:
        self._by_index: dict[int, StreamingToolCall] = {}
        self._by_id: dict[str, StreamingToolCall] = {}

    def consume(self, delta: object) -> tuple[StreamingToolCall, bool, str]:
        raw_index = _field(delta, "index")
        call_id = _field(delta, "id")
        call = None
        if isinstance(raw_index, int) and not isinstance(raw_index, bool) and raw_index >= 0:
            call = self._by_index.get(raw_index)
            stream_index = raw_index
        elif isinstance(call_id, str) and call_id:
            call = self._by_id.get(call_id)
            stream_index = call.stream_index if call is not None else len(self._by_index)
        else:
            raise ToolCallAssemblyError("DeepSeek tool call delta has no index or id")

        created = call is None
        if call is None:
            if self._by_index and stream_index <= max(self._by_index):
                raise ToolCallAssemblyError("DeepSeek introduced tool calls out of index order")
            call = StreamingToolCall(stream_index=stream_index)
            self._by_index[stream_index] = call
        fragment = call.consume(delta)
        if call.id:
            existing = self._by_id.get(call.id)
            if existing is not None and existing is not call:
                raise ToolCallAssemblyError("DeepSeek reused a streamed tool call id")
            self._by_id[call.id] = call
        return call, created, fragment


__all__ = ["StreamingToolCall", "ToolCallAssembler", "ToolCallAssemblyError"]
