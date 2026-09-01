"""Registration facade handed to a single extension."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from .auth_api import ExtensionAuthApi
from .context import ExtensionActions
from .hooks import Handler, HookRunner
from .registry import CapabilityRegistry, FlagState, Registration, RegistrationKind
from .renderers import ExtensionRendererRegistry
from .ui_api import ExtensionUiApi

_ACTION_NAMES = frozenset(
    {
        "abort",
        "append_entry",
        "compact",
        "cwd",
        "exec",
        "get_active_tools",
        "get_all_tools",
        "get_commands",
        "get_context_usage",
        "get_session_name",
        "get_system_prompt",
        "get_thinking_level",
        "has_pending_messages",
        "is_idle",
        "is_project_trusted",
        "model",
        "send_message",
        "send_user_message",
        "set_active_tools",
        "set_label",
        "set_model",
        "set_session_name",
        "set_thinking_level",
        "shutdown",
        "signal",
    }
)


class ExtensionAPI:
    """Registers capabilities on behalf of one extension into one registry."""

    __slots__ = ("_actions", "_auth", "_hooks", "_name", "_registry", "_renderers", "_ui")

    def __init__(
        self,
        name: str,
        *,
        registry: CapabilityRegistry | None = None,
        hooks: HookRunner | None = None,
        actions: ExtensionActions | None = None,
        ui: ExtensionUiApi | None = None,
        auth: ExtensionAuthApi | None = None,
        renderers: ExtensionRendererRegistry | None = None,
    ) -> None:
        self._name = name
        self._registry = registry if registry is not None else CapabilityRegistry()
        self._hooks = hooks if hooks is not None else HookRunner()
        self._actions = actions if actions is not None else ExtensionActions()
        self._ui = ui if ui is not None else ExtensionUiApi()
        self._auth = auth if auth is not None else ExtensionAuthApi()
        self._renderers = renderers if renderers is not None else ExtensionRendererRegistry()

    @property
    def registry(self) -> CapabilityRegistry:
        return self._registry

    @property
    def ui(self) -> ExtensionUiApi:
        return self._ui

    @property
    def auth(self) -> ExtensionAuthApi:
        return self._auth

    def _define(
        self, kind: RegistrationKind, name: str, payload: object | None = None
    ) -> Registration:
        return self._registry.register(kind, name, self._name, payload)

    def define_tool(self, name: str, tool: object | None = None) -> Registration:
        return self._define("tool", name, tool)

    def define_command(self, name: str, handler: object | None = None) -> Registration:
        return self._define("command", name, handler)

    def define_provider(self, name: str, provider: object | None = None) -> Registration:
        return self._define("provider", name, provider)

    def define_flag(
        self,
        name: str,
        *,
        value_type: Literal["boolean", "string"] = "boolean",
        default: bool | str | None = None,
    ) -> Registration:
        state = FlagState(value_type=value_type, value=None)
        state.set(default)
        return self._define("flag", name, state)

    def get_flag(self, name: str) -> bool | str | None:
        registration = self._registry.lookup("flag", name)
        if registration is None or registration.source != self._name:
            return None
        state = registration.payload
        return state.value if isinstance(state, FlagState) else None

    def set_flag(self, name: str, value: bool | str | None) -> None:
        registration = self._registry.lookup("flag", name)
        if registration is None or registration.source != self._name:
            raise LookupError(f"flag {name!r} is not registered by {self._name!r}")
        state = registration.payload
        if not isinstance(state, FlagState):
            raise TypeError(f"flag {name!r} has no mutable state")
        state.set(value)

    def define_shortcut(self, name: str, handler: object | None = None) -> Registration:
        return self._define("shortcut", name, handler)

    def define_message_renderer(
        self, custom_type: str, renderer: Callable[[object], object]
    ) -> None:
        self._renderers.register_message(self._name, custom_type, renderer)

    def define_entry_renderer(self, custom_type: str, renderer: Callable[[object], object]) -> None:
        self._renderers.register_entry(self._name, custom_type, renderer)

    def define_tool_renderer(
        self,
        tool_name: str,
        *,
        render_call: Callable[[object], object] | None = None,
        render_result: Callable[[object], object] | None = None,
    ) -> None:
        self._renderers.register_tool(
            self._name,
            tool_name,
            render_call=render_call,
            render_result=render_result,
        )

    def define_markdown_transformer(self, transformer: Callable[[str], str]) -> None:
        self._renderers.register_markdown(self._name, transformer)

    def on(self, event: str, handler: Handler) -> Callable[[], None]:
        """Register an ordered lifecycle handler for this extension generation."""
        return self._hooks.register(event, handler)

    def __getattr__(self, name: str) -> object:
        """Expose the stable action names directly, matching the upstream facade."""
        if name not in _ACTION_NAMES:
            raise AttributeError(name)
        try:
            return getattr(self._actions, name)
        except AttributeError:
            raise AttributeError(name) from None


__all__ = ["ExtensionAPI"]
