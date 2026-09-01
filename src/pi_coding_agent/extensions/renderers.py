"""Generation-owned renderer registry consumed by the product TUI."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .registry import RegistryConflictError


@dataclass(frozen=True, slots=True)
class _OwnedRenderer:
    source: str
    handler: Callable[[object], object]


@dataclass(frozen=True, slots=True)
class _ToolRenderers:
    source: str
    render_call: Callable[[object], object] | None
    render_result: Callable[[object], object] | None


class ExtensionRendererRegistry:
    """Stores extension render callbacks and isolates rendering failures."""

    __slots__ = ("_entries", "_markdown", "_messages", "_tools")

    def __init__(self) -> None:
        self._messages: dict[str, _OwnedRenderer] = {}
        self._entries: dict[str, _OwnedRenderer] = {}
        self._tools: dict[str, _ToolRenderers] = {}
        self._markdown: list[tuple[str, Callable[[str], str]]] = []

    def register_message(
        self, source: str, custom_type: str, renderer: Callable[[object], object]
    ) -> None:
        self._register(self._messages, "message", source, custom_type, renderer)

    def register_entry(
        self, source: str, custom_type: str, renderer: Callable[[object], object]
    ) -> None:
        self._register(self._entries, "entry", source, custom_type, renderer)

    def register_tool(
        self,
        source: str,
        tool_name: str,
        *,
        render_call: Callable[[object], object] | None,
        render_result: Callable[[object], object] | None,
    ) -> None:
        if tool_name in self._tools:
            raise RegistryConflictError(f"tool renderer {tool_name!r} already registered")
        self._tools[tool_name] = _ToolRenderers(source, render_call, render_result)

    def register_markdown(self, source: str, transformer: Callable[[str], str]) -> None:
        self._markdown.append((source, transformer))

    def render_message(self, custom_type: str, payload: object) -> str | None:
        return self._render(self._messages.get(custom_type), payload)

    def render_entry(self, custom_type: str, payload: object) -> str | None:
        return self._render(self._entries.get(custom_type), payload)

    def render_tool_call(self, tool_name: str, payload: object) -> str | None:
        renderers = self._tools.get(tool_name)
        return self._invoke(renderers.render_call, payload) if renderers is not None else None

    def render_tool_result(self, tool_name: str, payload: object) -> str | None:
        renderers = self._tools.get(tool_name)
        return self._invoke(renderers.render_result, payload) if renderers is not None else None

    def transform_markdown(self, markdown: str) -> str:
        transformed = markdown
        for _source, transformer in self._markdown:
            try:
                transformed = transformer(transformed)
            except Exception:
                continue
        return transformed

    def remove_source(self, source: str) -> None:
        self._messages = {
            name: renderer for name, renderer in self._messages.items() if renderer.source != source
        }
        self._entries = {
            name: renderer for name, renderer in self._entries.items() if renderer.source != source
        }
        self._tools = {
            name: renderers for name, renderers in self._tools.items() if renderers.source != source
        }
        self._markdown = [item for item in self._markdown if item[0] != source]

    @staticmethod
    def _register(
        registry: dict[str, _OwnedRenderer],
        kind: str,
        source: str,
        name: str,
        renderer: Callable[[object], object],
    ) -> None:
        if name in registry:
            raise RegistryConflictError(f"{kind} renderer {name!r} already registered")
        registry[name] = _OwnedRenderer(source, renderer)

    @classmethod
    def _render(cls, renderer: _OwnedRenderer | None, payload: object) -> str | None:
        return cls._invoke(renderer.handler, payload) if renderer is not None else None

    @staticmethod
    def _invoke(renderer: Callable[[object], object] | None, payload: object) -> str | None:
        if renderer is None:
            return None
        try:
            result = renderer(payload)
        except Exception:
            return None
        return result if isinstance(result, str) else None


__all__ = ["ExtensionRendererRegistry"]
