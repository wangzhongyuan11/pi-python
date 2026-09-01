"""Asynchronous SDK composition shared by future CLI and TUI adapters."""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Literal, Protocol, Self, cast, runtime_checkable
from uuid import uuid4

from pydantic import BaseModel

from pi_agent import (
    AfterToolCallContext,
    AfterToolCallResult,
    Agent,
    AgentMessage,
    AgentTool,
    BeforeToolCallContext,
    BeforeToolCallResult,
)
from pi_ai import (
    AssistantStream,
    Context,
    CredentialResolver,
    ImageContent,
    Model,
    ModelThinkingLevel,
    StreamOptions,
    TextContent,
    Usage,
    clamp_thinking_level,
)

from .agent_session import AgentSession
from .agent_session_runtime import (
    AgentSessionRuntime,
    RuntimeComponents,
    RuntimeEventSink,
    RuntimeTarget,
)
from .bootstrap import BootstrapConfig, ProductBootstrap, bootstrap
from .branch_summary import BranchSummarizer, BranchSummaryService
from .builtin_extensions.permission_gate import PermissionGate
from .compaction.cutpoint import TokenCounter, estimate_entry_tokens
from .compaction.model_summarizer import ModelRuntimeSummarizer
from .compaction.service import CompactionService
from .compaction.summarizer import CompactionSummarizer
from .deepseek_credentials import DeepSeekCredentialResolver
from .extensions.events import (
    BeforeProviderHeadersEvent,
    BeforeProviderRequestEvent,
    ContextEvent,
    ContextEventResult,
    ToolCallEvent,
    ToolCallEventResult,
    ToolResultEvent,
)
from .extensions.hooks import HookOutcome
from .model_runtime import ModelRuntime, create_model_runtime
from .ports import ExtensionRuntime, Settings
from .prompts.system import build_system_prompt
from .services import ProductServices, ServiceOverrides, create_product_services
from .session.context import project_session_context
from .session.importer import import_pi_session as _import_pi_session
from .session.manager import SessionManager
from .session.models import ImportResult
from .session.tree import SessionTree
from .tools.binaries import default_binary_cache_dir
from .tools.registry import ALL_TOOL_NAMES, DEFAULT_CODING_TOOL_NAMES, create_all_tools


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _hook_values(outcomes: Sequence[object]) -> tuple[object, ...]:
    return tuple(
        outcome.value
        for outcome in outcomes
        if isinstance(outcome, HookOutcome) and outcome.ok and outcome.value is not None
    )


async def _transform_extension_context(
    extensions: ExtensionRuntime,
    messages: Sequence[AgentMessage],
) -> tuple[AgentMessage, ...]:
    event = ContextEvent(messages=tuple(messages))

    def apply_result(raw_event: object, value: object) -> None:
        current_event = cast("ContextEvent", raw_event)
        if isinstance(value, ContextEventResult) and value.messages is not None:
            current_event.messages = value.messages
        elif isinstance(value, Mapping):
            mapping = cast("Mapping[str, object]", value)
            replacement = mapping.get("messages")
            if isinstance(replacement, Sequence):
                current_event.messages = tuple(cast("Sequence[AgentMessage]", replacement))

    await extensions.emit_chained(event, apply_result)
    return event.messages


def _stream_with_extension_hooks(
    extensions: ExtensionRuntime,
    model_runtime: ModelRuntime,
    model: Model,
    context: Context,
    options: StreamOptions | None = None,
) -> AssistantStream:
    async def on_payload(payload: object, _model: Model) -> object:
        request_event = BeforeProviderRequestEvent(payload=payload)

        def apply_result(raw_event: object, value: object) -> None:
            cast("BeforeProviderRequestEvent", raw_event).payload = value

        await extensions.emit_chained(request_event, apply_result)
        return request_event.payload

    async def transform_headers(
        headers: dict[str, str | None], _model: Model
    ) -> Mapping[str, str | None]:
        headers_event = BeforeProviderHeadersEvent(headers=headers)
        await extensions.emit(headers_event)
        return headers_event.headers

    hooked_options = replace(
        options or StreamOptions(),
        on_payload=on_payload,
        transform_headers=transform_headers,
    )
    return model_runtime.stream(model, context, hooked_options)


async def _before_extension_tool_call(
    extensions: ExtensionRuntime,
    context: BeforeToolCallContext,
) -> BeforeToolCallResult:
    args = context.args
    input_value: dict[str, object]
    if isinstance(args, BaseModel):
        input_value = cast("dict[str, object]", args.model_dump(mode="python"))
    elif isinstance(args, Mapping):
        input_value = dict(cast("Mapping[str, object]", args))
    else:
        input_value = {name: value for name, value in context.tool_call.arguments.items()}
    event = ToolCallEvent(
        tool_call_id=context.tool_call.id,
        tool_name=context.tool_call.name,
        input=input_value,
    )
    values = _hook_values(await extensions.emit(event))
    block = False
    reason: str | None = None
    terminate = False
    for value in values:
        if isinstance(value, ToolCallEventResult):
            block = block or value.block
            reason = value.reason if value.reason is not None else reason
            terminate = terminate or value.terminate
        elif isinstance(value, Mapping):
            mapping = cast("Mapping[str, object]", value)
            block = block or mapping.get("block") is True
            if isinstance(mapping.get("reason"), str):
                reason = cast("str", mapping["reason"])
            terminate = terminate or mapping.get("terminate") is True
    return BeforeToolCallResult(
        block=block,
        reason=reason,
        terminate=terminate,
        arguments=event.input,
    )


async def _after_extension_tool_call(
    extensions: ExtensionRuntime,
    context: AfterToolCallContext,
) -> AfterToolCallResult:
    input_value: dict[str, object]
    if isinstance(context.args, BaseModel):
        input_value = cast("dict[str, object]", context.args.model_dump(mode="python"))
    else:
        input_value = {name: value for name, value in context.tool_call.arguments.items()}
    event = ToolResultEvent(
        tool_call_id=context.tool_call.id,
        tool_name=context.tool_call.name,
        input=input_value,
        content=context.result.content,
        details=context.result.details,
        is_error=context.is_error,
        usage=context.result.usage,
    )

    def apply_result(raw_event: object, value: object) -> None:
        current_event = cast("ToolResultEvent", raw_event)
        if not isinstance(value, Mapping):
            return
        mapping = cast("Mapping[str, object]", value)
        content = mapping.get("content")
        if isinstance(content, Sequence):
            blocks = cast("Sequence[object]", content)
            if all(isinstance(block, TextContent | ImageContent) for block in blocks):
                current_event.content = tuple(cast("Sequence[TextContent | ImageContent]", blocks))
        if "details" in mapping:
            current_event.details = mapping["details"]
        if isinstance(mapping.get("is_error"), bool):
            current_event.is_error = cast("bool", mapping["is_error"])
        usage = mapping.get("usage")
        if isinstance(usage, Usage) or usage is None and "usage" in mapping:
            current_event.usage = usage

    await extensions.emit_chained(event, apply_result)
    return AfterToolCallResult(
        content=event.content,
        details=event.details,
        is_error=event.is_error,
        usage=event.usage,
    )


def default_session_dir(cwd: Path) -> Path:
    """Per-project default session directory under the agent home."""
    encoded = str(cwd).lstrip("/\\").replace("/", "-").replace("\\", "-").replace(":", "-")
    configured = os.environ.get("PI_PYTHON_AGENT_DIR")
    agent_dir = (
        Path(configured).expanduser() if configured else Path.home() / ".pi-python" / "agent"
    )
    return agent_dir.resolve() / "sessions" / f"--{encoded}--"


def _restore_thinking_level(value: str) -> ModelThinkingLevel:
    if value not in {"off", "minimal", "low", "medium", "high", "xhigh", "max"}:
        raise ValueError(f"invalid restored thinking level: {value}")
    return cast("ModelThinkingLevel", value)


def _default_tools_setting(settings: Settings) -> tuple[str, ...] | None:
    value = settings.get("defaultTools")
    if value is None or not isinstance(value, list):
        return None
    if not all(isinstance(item, str) for item in value):
        raise ValueError("defaultTools must be a list of tool names")
    if not value:
        return None
    known = set(ALL_TOOL_NAMES)
    return tuple(item for item in value if item in known)


def _reserve_tokens_setting(settings: Settings) -> int:
    value = settings.get("compaction")
    if not isinstance(value, dict):
        return 16_384
    reserve = cast("dict[str, object]", value).get("reserveTokens")
    if isinstance(reserve, int) and not isinstance(reserve, bool) and reserve >= 0:
        return reserve
    return 16_384


def _keep_recent_tokens_setting(settings: Settings) -> int:
    value = settings.get("compaction")
    if not isinstance(value, dict):
        return 20_000
    keep_recent = cast("dict[str, object]", value).get("keepRecentTokens")
    if isinstance(keep_recent, int) and not isinstance(keep_recent, bool) and keep_recent >= 0:
        return keep_recent
    return 20_000


@runtime_checkable
class _BuildsSystemPrompt(Protocol):
    def build_system_prompt(self, cwd: Path) -> str: ...


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolSelection:
    """CLI/TUI-facing built-in and extension tool selection."""

    no_tools: Literal["all", "builtin"] | None = None
    tool_names: tuple[str, ...] | None = None
    exclude_tools: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class CreateAgentSessionOptions:
    cwd: Path = field(default_factory=Path.cwd)
    service_overrides: ServiceOverrides = field(default_factory=ServiceOverrides)
    project_trusted: bool = False
    model_runtime: ModelRuntime | None = None
    credential_resolver: CredentialResolver | None = None
    session_manager: SessionManager | None = None
    system_prompt: str | None = None
    thinking_level: ModelThinkingLevel = "high"
    tools: tuple[AgentTool[Any, Any], ...] | None = None
    no_tools: Literal["all", "builtin"] | None = None
    tool_names: tuple[str, ...] | None = None
    exclude_tools: tuple[str, ...] | None = None
    permission_gate: PermissionGate | None = None
    agent_clock: Callable[[], int] | None = None
    entry_id_factory: Callable[[], str] = lambda: uuid4().hex
    timestamp_factory: Callable[[], str] = _timestamp
    compaction_summarizer: CompactionSummarizer | None = None
    compaction_keep_recent_tokens: int | None = None
    compaction_reserve_tokens: int = 16_384
    auto_compaction_enabled: bool = True
    compaction_token_count: TokenCounter = estimate_entry_tokens
    branch_summarizer: BranchSummarizer | None = None


class CreatedAgentSession:
    __slots__ = ("_bootstrap", "_closed", "_model_runtime", "_runtime")

    def __init__(
        self,
        *,
        product_bootstrap: ProductBootstrap,
        model_runtime: ModelRuntime,
        runtime: AgentSessionRuntime[AgentSession, ProductServices],
    ) -> None:
        self._bootstrap = product_bootstrap
        self._model_runtime = model_runtime
        self._runtime = runtime
        self._closed = False

    @property
    def session(self) -> AgentSession:
        return self._runtime.session

    @property
    def services(self) -> ProductServices:
        return self._runtime.services

    @property
    def model_runtime(self) -> ModelRuntime:
        return self._model_runtime

    @property
    def product_bootstrap(self) -> ProductBootstrap:
        return self._bootstrap

    async def new_session(self, manager: SessionManager) -> bool:
        return await self._runtime.new_session(manager)

    async def resume(
        self,
        manager: SessionManager,
        *,
        cwd_override: Path | None = None,
    ) -> bool:
        return await self._runtime.resume(manager, cwd_override=cwd_override)

    async def switch(self, manager: SessionManager) -> bool:
        return await self._runtime.switch(manager)

    async def fork(self, manager: SessionManager) -> bool:
        return await self._runtime.fork(manager)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._runtime.close()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exception_type, exception, traceback
        await self.close()


type AgentSessionFactory = Callable[[CreateAgentSessionOptions], Awaitable[CreatedAgentSession]]


async def create_agent_session(
    options: CreateAgentSessionOptions | None = None,
) -> CreatedAgentSession:
    selected = CreateAgentSessionOptions() if options is None else options
    cwd = selected.cwd.resolve()
    manager = selected.session_manager or SessionManager.create(
        cwd=cwd,
        session_dir=default_session_dir(cwd),
        session_id=uuid4().hex,
        timestamp=selected.timestamp_factory(),
    )
    manager_cwd = Path(manager.header.cwd).resolve()
    if manager_cwd != cwd:
        raise ValueError(f"session cwd {manager_cwd} does not match requested cwd {cwd}")

    product_bootstrap = bootstrap(
        BootstrapConfig(cwd=cwd, service_overrides=selected.service_overrides)
    )
    resolver = selected.credential_resolver or DeepSeekCredentialResolver(cwd=cwd)
    model_runtime = selected.model_runtime or create_model_runtime(
        credential_resolver=resolver,
        thinking_level=selected.thinking_level,
    )
    base_provider_id = model_runtime.provider.id
    base_model_id = model_runtime.model.id
    extension_provider_ids: set[str] = set()

    async def factory(
        target: RuntimeTarget,
    ) -> RuntimeComponents[AgentSession, ProductServices]:
        services = (
            product_bootstrap.services
            if target.generation == 0
            else create_product_services(target.cwd, selected.service_overrides)
        )
        if selected.project_trusted:
            services.reload_project_trust(True)
        if extension_provider_ids:
            if model_runtime.provider.id in extension_provider_ids:
                model_runtime.select_model(base_model_id, provider_id=base_provider_id)
            for provider_id in tuple(extension_provider_ids):
                model_runtime.unregister_provider(provider_id)
            extension_provider_ids.clear()
        services.resources.discover(target.cwd)
        await services.extensions.start()
        for provider in services.extensions.providers:
            model_runtime.register_provider(provider)
            extension_provider_ids.add(provider.id)
        messages = ()
        agent_model = model_runtime.model
        thinking_level = selected.thinking_level
        if target.session_manager.leaf_id is not None:
            tree = SessionTree.build(target.session_manager.entries)
            context = project_session_context(tree, target.session_manager.leaf_id)
            messages = context.messages
            if context.model is not None:
                agent_model = model_runtime.select_model(
                    context.model.model_id,
                    provider_id=context.model.provider,
                )
            thinking_level = clamp_thinking_level(
                agent_model, _restore_thinking_level(context.thinking_level)
            )
        shell_path = services.settings.get("shellPath")
        if shell_path is not None and not isinstance(shell_path, str):
            raise ValueError("shellPath must be a string")
        configured_default_tools = _default_tools_setting(services.settings)
        excluded_tools = set(selected.exclude_tools or ())
        if selected.tool_names is not None:
            builtin_names = tuple(name for name in selected.tool_names if name in ALL_TOOL_NAMES)
        elif selected.no_tools is not None:
            builtin_names = ()
        elif configured_default_tools is not None:
            builtin_names = configured_default_tools
        else:
            builtin_names = DEFAULT_CODING_TOOL_NAMES
        builtin_names = tuple(name for name in builtin_names if name not in excluded_tools)
        shell_command_prefix = services.settings.get("shellCommandPrefix")
        if shell_command_prefix is not None and not isinstance(shell_command_prefix, str):
            raise ValueError("shellCommandPrefix must be a string")
        session_manager = target.session_manager

        def session_environment() -> dict[str, str]:
            model = model_runtime.model
            environment = {
                "PI_SESSION_ID": session_manager.header.id,
                "PI_PROVIDER": model.provider,
                "PI_MODEL": model.id,
                "PI_REASONING_LEVEL": thinking_level,
            }
            if session_manager.path is not None:
                environment["PI_SESSION_FILE"] = str(session_manager.path)
            return environment

        configured_tools = (
            selected.tools
            if selected.tools is not None
            else create_all_tools(
                cwd=target.cwd,
                custom_shell_path=shell_path,
                tool_names=builtin_names,
                session_environment_provider=session_environment,
                command_prefix=shell_command_prefix,
                bin_dir=default_binary_cache_dir(),
            )
        )
        extension_tools = services.extensions.tools
        if selected.no_tools == "all":
            extension_tools = ()
        extension_tools = tuple(tool for tool in extension_tools if tool.name not in excluded_tools)
        registered_tools = (*configured_tools, *extension_tools)
        tool_names = [tool.name for tool in registered_tools]
        if len(set(tool_names)) != len(tool_names):
            raise ValueError("duplicate tool names across configured and extension tools")
        tools = (
            registered_tools
            if selected.permission_gate is None
            else selected.permission_gate.wrap_tools(registered_tools)
        )
        agent = Agent(
            model=agent_model,
            stream_function=lambda model, context, options=None: _stream_with_extension_hooks(
                services.extensions, model_runtime, model, context, options
            ),
            system_prompt=(
                services.resources.build_system_prompt(target.cwd)
                if selected.system_prompt is None
                and isinstance(services.resources, _BuildsSystemPrompt)
                else (
                    build_system_prompt(cwd=target.cwd)
                    if selected.system_prompt is None
                    else selected.system_prompt
                )
            ),
            thinking_level=thinking_level,
            tools=tools,
            messages=messages,
            transform_context=lambda messages: _transform_extension_context(
                services.extensions, messages
            ),
            before_tool_call=lambda context: _before_extension_tool_call(
                services.extensions, context
            ),
            after_tool_call=lambda context: _after_extension_tool_call(
                services.extensions, context
            ),
            clock=selected.agent_clock,
        )
        compaction_service = CompactionService(
            session_manager=target.session_manager,
            summarizer=(
                selected.compaction_summarizer
                if selected.compaction_summarizer is not None
                else ModelRuntimeSummarizer(model_runtime=model_runtime)
            ),
            entry_id_factory=selected.entry_id_factory,
            timestamp_factory=selected.timestamp_factory,
        )
        branch_summary_service = (
            BranchSummaryService(
                session_manager=target.session_manager,
                summarizer=selected.branch_summarizer,
                entry_id_factory=selected.entry_id_factory,
                timestamp_factory=selected.timestamp_factory,
            )
            if selected.branch_summarizer is not None
            else None
        )

        async def close_services(_reason: object) -> None:
            await services.extensions.close()

        session = AgentSession(
            agent=agent,
            session_manager=target.session_manager,
            services=services,
            entry_id_factory=selected.entry_id_factory,
            timestamp_factory=selected.timestamp_factory,
            compaction_service=compaction_service,
            compaction_keep_recent_tokens=(
                selected.compaction_keep_recent_tokens
                if selected.compaction_keep_recent_tokens is not None
                else _keep_recent_tokens_setting(services.settings)
            ),
            compaction_reserve_tokens=_reserve_tokens_setting(services.settings),
            auto_compaction_enabled=selected.auto_compaction_enabled,
            compaction_token_count=selected.compaction_token_count,
            branch_summary_service=branch_summary_service,
            on_close=close_services,
        )
        return RuntimeComponents(
            session=session,
            services=services,
            events=(
                cast("RuntimeEventSink", services.extensions)
                if callable(getattr(services.extensions, "emit", None))
                else None
            ),
        )

    runtime = await AgentSessionRuntime[AgentSession, ProductServices].create(
        factory,
        cwd=cwd,
        session_manager=manager,
    )
    return CreatedAgentSession(
        product_bootstrap=product_bootstrap,
        model_runtime=model_runtime,
        runtime=runtime,
    )


def import_pi_session(
    source: str | Path,
    *,
    session_dir: str | Path | None = None,
) -> ImportResult:
    return _import_pi_session(source, session_dir=session_dir)


__all__ = [
    "AgentSessionFactory",
    "CreateAgentSessionOptions",
    "CreatedAgentSession",
    "create_agent_session",
    "default_session_dir",
    "import_pi_session",
]
