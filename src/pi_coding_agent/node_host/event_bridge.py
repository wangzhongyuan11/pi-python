"""Node extension host event and action bridging (P15.5-T04).

Node handlers participate in the *default* extension event fan-out: for every
event a bridged extension subscribed to, a Python forwarder is registered on
the shared HookRunner, so ordering, chaining, and error isolation match native
Python extensions. Session actions requested by the host are routed to the
bound product actions; stale generations reject everything.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import fields as dataclass_fields
from dataclasses import is_dataclass
from typing import Protocol, cast

HostCaller = Callable[[str, Mapping[str, object]], Awaitable[object]]
Handler = Callable[..., object]


class ExtensionActionsProtocol(Protocol):
    """The subset of ExtensionActions the node host may invoke."""

    def send_message(
        self,
        custom_type: str,
        content: str,
        *,
        display: bool = True,
        details: object = None,
        trigger_turn: bool = False,
        deliver_as: str = "follow_up",
    ) -> object: ...

    def send_user_message(self, content: str, *, deliver_as: str = "follow_up") -> object: ...

    def append_entry(self, custom_type: str, data: object = None) -> str: ...

    def set_session_name(self, name: str) -> str: ...

    def get_session_name(self) -> str | None: ...

    def set_label(self, entry_id: str, label: str | None) -> str: ...

    async def exec(
        self,
        command: str,
        args: tuple[str, ...],
        *,
        cwd: object = None,
        timeout: float | None = None,
    ) -> object: ...

    def get_active_tools(self) -> tuple[str, ...]: ...

    def set_active_tools(self, names: tuple[str, ...] | list[str]) -> None: ...

    def get_commands(self) -> tuple[object, ...]: ...

    def set_model(self, model: str) -> bool: ...

    def get_thinking_level(self) -> str: ...

    def set_thinking_level(self, level: str) -> None: ...


class NodeHostStaleError(RuntimeError):
    """A stale host generation attempted to interact with the product."""


class NodeRequestError(RuntimeError):
    """The host requested an operation no bridge can perform."""


def to_camel_key(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(part.title() for part in parts[1:])


def serialize_event(event: object) -> object:
    """Serialize a Python extension event dataclass to camelCase wire JSON."""

    if is_dataclass(event) and not isinstance(event, type):
        return {
            to_camel_key(field.name): serialize_event(getattr(event, field.name))
            for field in dataclass_fields(event)
        }
    if isinstance(event, tuple | list):
        items = cast("list[object]", event)
        return [serialize_event(item) for item in items]
    if isinstance(event, dict):
        mapping = cast("dict[object, object]", event)
        return {str(key): serialize_event(value) for key, value in mapping.items()}
    return event


def _as_mapping(value: object) -> Mapping[str, object]:
    return cast("Mapping[str, object]", value if isinstance(value, Mapping) else {})


def _result_of(raw: object) -> object:
    mapping = _as_mapping(raw)
    if mapping:
        return mapping.get("result")
    return raw


class NodeEventBridge:
    """Forward shared-hook events to the host and track subscriptions."""

    def __init__(self, *, host_caller: HostCaller, generation: int = 0) -> None:
        self._host_caller = host_caller
        self._generation = generation
        self._stale = False
        self._unsubscribers: list[Callable[[], None]] = []

    def register_forwarders(
        self,
        hooks: object,
        events: Mapping[str, str],
        *,
        source: str = "node-host",
    ) -> tuple[str, ...]:
        """Register a Python forwarder per subscribed event on the HookRunner."""

        del source
        if self._stale:
            raise NodeHostStaleError("node host generation is stale")
        register = getattr(hooks, "register", None)
        if not callable(register):
            raise TypeError("hooks must expose register(event, handler)")
        registered: tuple[str, ...] = ()
        for event_name, node_event in events.items():
            forwarder = self._make_forwarder(node_event)
            unregister = cast("Callable[[], None]", register(event_name, forwarder))
            self._unsubscribers.append(unregister)
            registered += (event_name,)
        return registered

    def _make_forwarder(self, node_event: str) -> Handler:
        async def forwarder(event: object) -> object:
            if self._stale:
                raise NodeHostStaleError("node host generation is stale")
            raw = await self._host_caller(
                "dispatch",
                {
                    "event": node_event,
                    "payload": serialize_event(event),
                    "context": {"hasUI": True, "generation": self._generation},
                },
            )
            return _result_of(raw)

        return forwarder

    def invalidate(self) -> None:
        self._stale = True
        for unregister in self._unsubscribers:
            unregister()
        self._unsubscribers.clear()


class NodeActionBridge:
    """Route host session-action requests to the bound product actions."""

    def __init__(
        self,
        *,
        actions_provider: Callable[[], ExtensionActionsProtocol | None],
    ) -> None:
        self._actions_provider = actions_provider
        self._stale = False

    async def handle_request(self, command: str, payload: Mapping[str, object]) -> object:
        if self._stale:
            raise NodeHostStaleError("node host generation is stale")
        actions = self._actions_provider()
        if actions is None:
            raise NodeHostStaleError("no session is bound to the node host")
        handler = getattr(self, f"_{command}", None)
        if not callable(handler):
            raise NodeRequestError(f"action bridge cannot handle {command!r}")
        return await cast("Callable[..., Awaitable[object]]", handler)(payload, actions)

    def invalidate(self) -> None:
        self._stale = True

    async def _send_message(
        self, payload: Mapping[str, object], actions: ExtensionActionsProtocol
    ) -> object:
        message = _as_mapping(payload.get("message"))
        options = _as_mapping(payload.get("options"))
        deliver = str(options.get("deliverAs", "followUp")).replace("followUp", "follow_up")
        return actions.send_message(
            str(message.get("customType", "")),
            str(message.get("content", "")),
            display=bool(message.get("display", True)),
            details=message.get("details"),
            trigger_turn=bool(options.get("triggerTurn", False)),
            deliver_as="steer" if deliver == "steer" else "follow_up",
        )

    async def _send_user_message(
        self, payload: Mapping[str, object], actions: ExtensionActionsProtocol
    ) -> object:
        options = _as_mapping(payload.get("options"))
        deliver = str(options.get("deliverAs", "followUp")).replace("followUp", "follow_up")
        content = payload.get("content")
        text = (
            str(content)
            if not isinstance(content, list)
            else "".join(
                str(_as_mapping(block).get("text", "")) for block in cast("list[object]", content)
            )
        )
        return actions.send_user_message(text, deliver_as=deliver)

    async def _append_entry(
        self, payload: Mapping[str, object], actions: ExtensionActionsProtocol
    ) -> object:
        return actions.append_entry(str(payload.get("customType", "")), payload.get("data"))

    async def _set_session_name(
        self, payload: Mapping[str, object], actions: ExtensionActionsProtocol
    ) -> object:
        return actions.set_session_name(str(payload.get("name", "")))

    async def _get_session_name(
        self, payload: Mapping[str, object], actions: ExtensionActionsProtocol
    ) -> object:
        del payload
        return actions.get_session_name()

    async def _set_label(
        self, payload: Mapping[str, object], actions: ExtensionActionsProtocol
    ) -> object:
        label = payload.get("label")
        return actions.set_label(
            str(payload.get("entryId", "")), str(label) if label is not None else None
        )

    async def _exec(
        self, payload: Mapping[str, object], actions: ExtensionActionsProtocol
    ) -> object:
        options = _as_mapping(payload.get("options"))
        raw_cwd = options.get("cwd")
        timeout = options.get("timeout")
        return await actions.exec(
            str(payload.get("command", "")),
            tuple(str(item) for item in cast("list[object]", payload.get("args") or ())),
            cwd=str(raw_cwd) if raw_cwd is not None else None,
            timeout=float(str(timeout)) if timeout is not None else None,
        )

    async def _get_active_tools(
        self, payload: Mapping[str, object], actions: ExtensionActionsProtocol
    ) -> object:
        del payload
        return list(actions.get_active_tools())

    async def _set_active_tools(
        self, payload: Mapping[str, object], actions: ExtensionActionsProtocol
    ) -> object:
        names = payload.get("toolNames")
        actions.set_active_tools(tuple(str(item) for item in cast("list[object]", names or ())))
        return {"ok": True}

    async def _get_commands(
        self, payload: Mapping[str, object], actions: ExtensionActionsProtocol
    ) -> object:
        del payload
        return [
            {"name": getattr(item, "name", ""), "description": getattr(item, "description", "")}
            for item in actions.get_commands()
        ]

    async def _set_model(
        self, payload: Mapping[str, object], actions: ExtensionActionsProtocol
    ) -> object:
        model = _as_mapping(payload.get("model"))
        provider = str(model.get("provider", ""))
        model_id = str(model.get("id", ""))
        argument = f"{provider}/{model_id}" if provider and model_id else model_id
        return {"ok": bool(actions.set_model(argument))}

    async def _get_thinking_level(
        self, payload: Mapping[str, object], actions: ExtensionActionsProtocol
    ) -> object:
        del payload
        return actions.get_thinking_level()

    async def _set_thinking_level(
        self, payload: Mapping[str, object], actions: ExtensionActionsProtocol
    ) -> object:
        actions.set_thinking_level(str(payload.get("level", "off")))
        return {"ok": True}


def combine_handlers(
    *bridges: object,
) -> Callable[[str, Mapping[str, object]], Awaitable[object]]:
    """Route a host request to the first bridge that claims the command."""

    async def handle(command: str, payload: Mapping[str, object]) -> object:
        for bridge in bridges:
            candidate = getattr(bridge, "handle_request", None)
            if callable(candidate):
                awaitable = cast("Callable[..., Awaitable[object]]", candidate)
                try:
                    return await awaitable(command, payload)
                except NodeRequestError:
                    continue
        raise NodeRequestError(f"no bridge handles {command!r}")

    return handle


__all__ = [
    "ExtensionActionsProtocol",
    "NodeActionBridge",
    "NodeEventBridge",
    "NodeHostStaleError",
    "NodeRequestError",
    "combine_handlers",
    "serialize_event",
]
