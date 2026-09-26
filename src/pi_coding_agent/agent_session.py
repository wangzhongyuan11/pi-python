"""Product facade that owns one Agent and its stable service ports."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from pi_agent import (
    Agent,
    AgentEndEvent,
    AgentEvent,
    AgentMessage,
    AgentStartEvent,
    AgentState,
    MessageEndEvent,
    MessageStartEvent,
    MessageUpdateEvent,
    ToolExecutionStartEvent,
    ToolExecutionUpdateEvent,
    TurnEndEvent,
    TurnStartEvent,
)
from pi_ai import (
    AssistantMessage,
    JsonValue,
    Model,
    ModelThinkingLevel,
    ToolCall,
    ToolResultMessage,
    UserMessage,
)
from pi_ai.wire.messages import dump_message

from .agent_session_events import (
    AgentSessionEvent,
    AgentSessionEventListener,
    AutoRetryEndEvent,
    AutoRetryStartEvent,
    CompactionEndEvent,
    CompactionStartEvent,
    EntryAppendedEvent,
)
from .agent_session_runtime import RuntimeReason
from .branch_summary import BranchSummaryService
from .branches import diff_branch_paths
from .compaction.cutpoint import (
    TokenCounter,
    choose_compaction_cutpoint,
    estimate_entry_tokens,
)
from .compaction.service import CompactionReason, CompactionService
from .context_overflow import OverflowRecovery, is_context_overflow
from .extensions.events import (
    AgentSettledEvent,
    ExtensionAgentEndEvent,
    ExtensionAgentStartEvent,
    ExtensionLifecycleEvent,
    ExtensionMessageEndEvent,
    ExtensionMessageStartEvent,
    ExtensionMessageUpdateEvent,
    ExtensionToolExecutionEndEvent,
    ExtensionToolExecutionStartEvent,
    ExtensionToolExecutionUpdateEvent,
    ExtensionTurnEndEvent,
    ExtensionTurnStartEvent,
    UiPromptEndEvent,
    UiPromptStartEvent,
)
from .extensions.session_context import (
    SessionBeforeCompactEvent,
    SessionBeforeTreeEvent,
    SessionCompactEvent,
    SessionTreeEvent,
    TreePreparation,
)
from .file_tracking import FileOperations
from .retry import RetryPolicy, Sleep, is_retryable_assistant_error
from .services import ProductServices
from .session.context import project_session_context
from .session.manager import SessionManager
from .session.models import (
    BranchSummaryEntry,
    CompactionEntry,
    CustomEntry,
    CustomMessageEntry,
    LabelEntry,
    MessageEntry,
    ModelChangeEntry,
    ThinkingLevelChangeEntry,
)
from .session.tree import SessionTree
from .tools.bash import BashResult


def _entry_id() -> str:
    return uuid4().hex


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class AgentSessionClosedError(RuntimeError):
    pass


class SessionOperationCancelled(RuntimeError):
    pass


class AgentSession:
    __slots__ = (
        "_branch_summary_service",
        "_closed",
        "_compaction_keep_recent_tokens",
        "_compaction_reserve_tokens",
        "_auto_compaction_enabled",
        "_is_compacting",
        "_compaction_service",
        "_compaction_token_count",
        "_entry_id_factory",
        "_listeners",
        "_on_close",
        "_overflow_recovery",
        "_retry_cancel",
        "_retry_policy",
        "_sleep",
        "_timestamp_factory",
        "_extension_turn_index",
        "_open_tool_calls",
        "_queued_pair_messages",
        "_unsubscribe_agent",
        "agent",
        "services",
        "session_manager",
    )

    def __init__(
        self,
        *,
        agent: Agent,
        session_manager: SessionManager,
        services: ProductServices,
        entry_id_factory: Callable[[], str] = _entry_id,
        timestamp_factory: Callable[[], str] = _timestamp,
        on_close: Callable[[RuntimeReason], object] | None = None,
        retry_policy: RetryPolicy | None = None,
        sleep: Sleep = asyncio.sleep,
        overflow_recovery: OverflowRecovery | None = None,
        compaction_service: CompactionService | None = None,
        compaction_keep_recent_tokens: int = 20_000,
        compaction_reserve_tokens: int = 16_384,
        auto_compaction_enabled: bool = True,
        compaction_token_count: TokenCounter = estimate_entry_tokens,
        branch_summary_service: BranchSummaryService | None = None,
    ) -> None:
        self.agent = agent
        self.session_manager = session_manager
        self.services = services
        self._entry_id_factory = entry_id_factory
        self._timestamp_factory = timestamp_factory
        self._on_close = on_close
        self._retry_policy = retry_policy or RetryPolicy()
        self._sleep = sleep
        self._retry_cancel = asyncio.Event()
        self._overflow_recovery = overflow_recovery
        self._compaction_service = compaction_service
        self._compaction_keep_recent_tokens = compaction_keep_recent_tokens
        self._compaction_reserve_tokens = compaction_reserve_tokens
        self._auto_compaction_enabled = auto_compaction_enabled
        self._is_compacting = False
        self._compaction_token_count = compaction_token_count
        self._branch_summary_service = branch_summary_service
        self._listeners: list[AgentSessionEventListener] = []
        self._extension_turn_index = 0
        self._open_tool_calls = 0
        self._queued_pair_messages: list[dict[str, JsonValue]] = []
        self._closed = False
        self._unsubscribe_agent = agent.subscribe(self._handle_agent_event)

    @property
    def state(self) -> AgentState:
        return self.agent.state

    @property
    def messages(self) -> tuple[AgentMessage, ...]:
        return self.agent.state.messages

    @property
    def is_closed(self) -> bool:
        return self._closed

    def subscribe(self, listener: AgentSessionEventListener) -> Callable[[], None]:
        self._ensure_open()
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    async def prompt(self, prompt: str | AgentMessage | Sequence[AgentMessage]) -> None:
        self._ensure_open()
        await self._emit_extension(UiPromptStartEvent(prompt=prompt))
        try:
            await self._run_prompt(prompt)
            await self._emit_extension(AgentSettledEvent())
        finally:
            await self._emit_extension(UiPromptEndEvent(prompt=prompt))

    async def _run_prompt(self, prompt: str | AgentMessage | Sequence[AgentMessage]) -> None:
        self._ensure_open()
        next_prompt: str | AgentMessage | Sequence[AgentMessage] = prompt
        self._retry_cancel = asyncio.Event()
        attempt = 0
        overflow_attempted = False
        while True:
            await self.agent.prompt(next_prompt)
            last = self.agent.state.messages[-1] if self.agent.state.messages else None
            if (
                isinstance(last, AssistantMessage)
                and is_context_overflow(last)
                and (self._overflow_recovery is not None or self._compaction_service is not None)
                and not overflow_attempted
            ):
                overflow_attempted = True
                self.agent.restore_messages(self.agent.state.messages[:-1])
                recovered = (
                    await self._overflow_recovery()
                    if self._overflow_recovery is not None
                    else await self._compact_for_overflow()
                )
                if recovered:
                    messages = self.agent.state.messages
                    if (
                        messages
                        and isinstance(messages[-1], AssistantMessage)
                        and is_context_overflow(messages[-1])
                    ):
                        self.agent.restore_messages(messages[:-1])
                    next_prompt = ()
                    continue
                return
            error = self._retryable_error()
            if error is None:
                if attempt:
                    await self._emit(
                        AutoRetryEndEvent(success=True, attempt=attempt), asyncio.Event()
                    )
                if isinstance(last, AssistantMessage):
                    await self._check_threshold_compaction(last)
                return
            if (
                not self._retry_policy.allows_turn_retry
                or attempt >= self._retry_policy.max_retries
                or self._retry_cancel.is_set()
            ):
                if attempt:
                    await self._emit(
                        AutoRetryEndEvent(success=False, attempt=attempt, final_error=error),
                        asyncio.Event(),
                    )
                return
            attempt += 1
            delay = self._retry_policy.delay(attempt)
            await self._emit(
                AutoRetryStartEvent(
                    attempt=attempt,
                    max_attempts=self._retry_policy.max_retries,
                    delay_seconds=delay,
                    error_message=error,
                ),
                asyncio.Event(),
            )
            if await self._wait_for_retry(delay):
                await self._emit(
                    AutoRetryEndEvent(
                        success=False, attempt=attempt, final_error="retry cancelled"
                    ),
                    asyncio.Event(),
                )
                return
            self.agent.restore_messages(self.agent.state.messages[:-1])
            next_prompt = ()

    def cancel_retry(self) -> None:
        self._retry_cancel.set()

    @property
    def auto_compaction_enabled(self) -> bool:
        return self._auto_compaction_enabled

    def set_auto_compaction_enabled(self, enabled: bool) -> None:
        self._auto_compaction_enabled = enabled

    @property
    def auto_retry_enabled(self) -> bool:
        return self._retry_policy.enabled

    def set_auto_retry_enabled(self, enabled: bool) -> None:
        self._retry_policy = RetryPolicy(
            enabled=enabled,
            max_retries=self._retry_policy.max_retries,
            base_delay_seconds=self._retry_policy.base_delay_seconds,
            provider_request_retries=self._retry_policy.provider_request_retries,
        )

    def append_custom_entry(self, custom_type: str, data: JsonValue = None) -> str:
        self._ensure_open()
        entry = CustomEntry(
            type="custom",
            id=self._entry_id_factory(),
            parent_id=self.session_manager.leaf_id,
            timestamp=self._timestamp_factory(),
            custom_type=custom_type,
            data=data,
        )
        self.session_manager.append(entry)
        return entry.id

    def record_bash_result(
        self, command: str, result: BashResult, *, exclude_from_context: bool = False
    ) -> None:
        self._ensure_open()
        if self.state.is_streaming:
            raise RuntimeError("cannot record user bash while Agent is streaming")
        payload: dict[str, JsonValue] = {
            "role": "bashExecution",
            "command": command,
            "output": result.output,
            "exitCode": result.exit_code,
            "cancelled": result.aborted,
            "truncated": result.truncated,
            "fullOutputPath": str(result.full_output_path) if result.full_output_path else None,
            "excludeFromContext": exclude_from_context,
            "timestamp": time.time_ns() // 1_000_000,
        }
        self.session_manager.append(
            MessageEntry(
                type="message",
                id=self._entry_id_factory(),
                parent_id=self.session_manager.leaf_id,
                timestamp=self._timestamp_factory(),
                message=payload,
            )
        )
        self._restore_active_context()

    def append_custom_message(
        self,
        custom_type: str,
        content: str,
        *,
        display: bool = True,
        details: JsonValue = None,
    ) -> str:
        self._ensure_open()
        if self._open_tool_calls > 0:
            # Queue the message until the open ToolCall/ToolResult pair settles;
            # inserting between them would split the pair in the session graph.
            self._queued_pair_messages.append(
                {
                    "custom_type": custom_type,
                    "content": content,
                    "display": display,
                    "details": details,
                }
            )
            return ""
        return self._append_custom_message_now(
            custom_type, content, display=display, details=details
        )

    def _append_custom_message_now(
        self,
        custom_type: str,
        content: str,
        *,
        display: bool = True,
        details: JsonValue = None,
    ) -> str:
        entry = CustomMessageEntry(
            type="custom_message",
            id=self._entry_id_factory(),
            parent_id=self.session_manager.leaf_id,
            timestamp=self._timestamp_factory(),
            custom_type=custom_type,
            content=content,
            display=display,
            details=details,
        )
        self.session_manager.append(entry)
        if not self.state.is_streaming:
            self._restore_active_context()
        return entry.id

    def _flush_queued_pair_messages(self) -> None:
        queued, self._queued_pair_messages = self._queued_pair_messages, []
        for item in queued:
            self._append_custom_message_now(
                cast("str", item["custom_type"]),
                cast("str", item["content"]),
                display=cast("bool", item["display"]),
                details=item["details"],
            )

    def set_session_name(self, name: str) -> str:
        self._ensure_open()
        return self.session_manager.append_session_info(
            name,
            entry_id_factory=self._entry_id_factory,
            timestamp_factory=self._timestamp_factory,
        )

    def set_label(self, entry_id: str, label: str | None) -> str:
        self._ensure_open()
        if entry_id not in {entry.id for entry in self.session_manager.entries}:
            raise LookupError(f"unknown session entry: {entry_id}")
        entry = LabelEntry(
            type="label",
            id=self._entry_id_factory(),
            parent_id=self.session_manager.leaf_id,
            timestamp=self._timestamp_factory(),
            target_id=entry_id,
            label=label,
        )
        self.session_manager.append(entry)
        return entry.id

    def set_model(self, model: Model) -> None:
        self._ensure_open()
        if self.state.model == model:
            return
        if self.state.is_streaming:
            raise RuntimeError("cannot change model while Agent is streaming")
        self.session_manager.append(
            ModelChangeEntry(
                type="model_change",
                id=self._entry_id_factory(),
                parent_id=self.session_manager.leaf_id,
                timestamp=self._timestamp_factory(),
                provider=model.provider,
                model_id=model.id,
            )
        )
        self.agent.set_model(model)

    def set_thinking_level(self, level: ModelThinkingLevel) -> None:
        self._ensure_open()
        if self.state.thinking_level == level:
            return
        if self.state.is_streaming:
            raise RuntimeError("cannot change thinking level while Agent is streaming")
        self.session_manager.append(
            ThinkingLevelChangeEntry(
                type="thinking_level_change",
                id=self._entry_id_factory(),
                parent_id=self.session_manager.leaf_id,
                timestamp=self._timestamp_factory(),
                thinking_level=level,
            )
        )
        self.agent.set_thinking_level(level)

    async def compact(
        self, *, reason: CompactionReason = "manual", custom_instructions: str | None = None
    ) -> CompactionEntry:
        self._ensure_open()
        if self._is_compacting:
            raise RuntimeError("compaction is already running")
        if self.state.is_streaming:
            raise RuntimeError("cannot compact while Agent is streaming")
        self._is_compacting = True
        try:
            return await self._compact(reason=reason, custom_instructions=custom_instructions)
        finally:
            self._is_compacting = False

    @property
    def is_compacting(self) -> bool:
        return self._is_compacting

    async def _compact(
        self, *, reason: CompactionReason, custom_instructions: str | None
    ) -> CompactionEntry:
        self._ensure_open()
        if self._compaction_service is None:
            raise RuntimeError("compaction is not configured for this AgentSession")
        path = self.session_manager.active_path()
        previous = next(
            (entry for entry in reversed(path) if isinstance(entry, CompactionEntry)), None
        )
        if previous is not None:
            # The next compaction starts at the previous first-kept entry: those
            # messages are still live context that must be summarized (upstream
            # prepareCompaction boundaryStart).
            kept_start = next(
                (
                    index
                    for index, entry in enumerate(path)
                    if entry.id == previous.first_kept_entry_id
                ),
                path.index(previous) + 1,
            )
            entries = path[kept_start:]
            previous_summary = previous.summary
        else:
            entries = path
            previous_summary = None
        cutpoint = choose_compaction_cutpoint(
            entries,
            keep_recent_tokens=self._compaction_keep_recent_tokens,
            token_count=self._compaction_token_count,
        )
        if cutpoint.first_kept_index == 0:
            # Upstream prepareCompaction returns undefined in this case: there is
            # nothing to summarize, so compacting would only drop live context.
            raise ValueError("nothing to compact: all recent entries are kept")
        extension_values = _extension_values(
            await self.services.extensions.emit(
                SessionBeforeCompactEvent(
                    preparation=cutpoint,
                    branch_entries=tuple(entries),
                    reason=reason,
                    will_retry=reason == "overflow",
                )
            )
        )
        if _cancelled(extension_values):
            raise SessionOperationCancelled("compaction cancelled by extension")
        await self._emit(CompactionStartEvent(reason=reason), asyncio.Event())
        tokens_before = sum(self._compaction_token_count(item) for item in entries)
        custom = _nested_mapping(extension_values, "compaction")
        custom_summary = None if custom is None else custom.get("summary")
        from_extension = isinstance(custom_summary, str)
        if isinstance(custom_summary, str) and custom is not None:
            first_kept = custom.get("first_kept_entry_id")
            first_kept_id = (
                first_kept if isinstance(first_kept, str) else entries[cutpoint.first_kept_index].id
            )
            if first_kept_id not in {item.id for item in entries}:
                raise ValueError("extension compaction selected an unknown kept entry")
            entry = CompactionEntry(
                type="compaction",
                id=self._entry_id_factory(),
                parent_id=self.session_manager.leaf_id,
                timestamp=self._timestamp_factory(),
                summary=custom_summary,
                first_kept_entry_id=first_kept_id,
                tokens_before=tokens_before,
                details=cast("JsonValue", custom.get("details")),
                from_hook=True,
            )
            self.session_manager.append(entry)
        else:
            entry = await self._compaction_service.compact(
                entries,
                cutpoint,
                reason=reason,
                tokens_before=tokens_before,
                previous_summary=previous_summary,
                custom_instructions=custom_instructions,
            )
        self._restore_active_context()
        await self.services.extensions.emit(
            SessionCompactEvent(
                compaction_entry=entry,
                from_extension=from_extension,
                reason=reason,
                will_retry=reason == "overflow",
            )
        )
        await self._emit(
            CompactionEndEvent(reason=reason, tokens_before=entry.tokens_before),
            asyncio.Event(),
        )
        return entry

    async def branch(
        self,
        target_id: str,
        *,
        summarize: bool = False,
        file_ops: FileOperations | None = None,
    ) -> BranchSummaryEntry | None:
        self._ensure_open()
        tree = SessionTree.build(self.session_manager.entries)
        target_path = tree.active_path(target_id)
        old_leaf_id = self.session_manager.leaf_id
        diff = diff_branch_paths(self.session_manager.active_path(), target_path)
        extension_values = _extension_values(
            await self.services.extensions.emit(
                SessionBeforeTreeEvent(
                    preparation=TreePreparation(
                        target_id=target_id,
                        old_leaf_id=old_leaf_id,
                        common_ancestor_id=diff.lca_id,
                        entries_to_summarize=diff.from_entries,
                        user_wants_summary=summarize,
                    )
                )
            )
        )
        if _cancelled(extension_values):
            raise SessionOperationCancelled("tree navigation cancelled by extension")
        custom = _nested_mapping(extension_values, "summary") if summarize else None
        custom_summary = None if custom is None else custom.get("summary")
        if not summarize:
            self.session_manager.branch(target_id)
            self._restore_active_context()
            await self.services.extensions.emit(
                SessionTreeEvent(
                    new_leaf_id=self.session_manager.leaf_id,
                    old_leaf_id=old_leaf_id,
                )
            )
            return None
        if isinstance(custom_summary, str) and custom is not None and diff.from_entries:
            self.session_manager.branch(target_id)
            entry = BranchSummaryEntry(
                type="branch_summary",
                id=self._entry_id_factory(),
                parent_id=target_id,
                timestamp=self._timestamp_factory(),
                from_id=diff.from_entries[-1].id,
                summary=custom_summary,
                details=cast("JsonValue", custom.get("details")),
                from_hook=True,
            )
            self.session_manager.append(entry)
            self._restore_active_context()
            await self.services.extensions.emit(
                SessionTreeEvent(
                    new_leaf_id=self.session_manager.leaf_id,
                    old_leaf_id=old_leaf_id,
                    summary_entry=entry,
                    from_extension=True,
                )
            )
            return entry
        if self._branch_summary_service is None:
            raise RuntimeError("branch summarization is not configured for this AgentSession")
        entry = await self._branch_summary_service.record(
            diff, target_id=target_id, file_ops=file_ops
        )
        if entry is None:
            self.session_manager.branch(target_id)
        self._restore_active_context()
        await self.services.extensions.emit(
            SessionTreeEvent(
                new_leaf_id=self.session_manager.leaf_id,
                old_leaf_id=old_leaf_id,
                summary_entry=entry,
            )
        )
        return entry

    def abort(self) -> None:
        self.cancel_retry()
        self.agent.abort()

    async def wait_for_idle(self) -> None:
        await self.agent.wait_for_idle()
        return None

    async def close(self, reason: RuntimeReason) -> None:
        if self._closed:
            return
        self._closed = True
        self.agent.abort()
        await self.agent.wait_for_idle()
        self._unsubscribe_agent()
        if self._on_close is not None:
            result = self._on_close(reason)
            if inspect.isawaitable(result):
                await result

    async def _handle_agent_event(self, event: AgentEvent, signal: asyncio.Event) -> None:
        await self._emit_agent_extension(event)
        entry: MessageEntry | None = None
        if isinstance(event, MessageEndEvent):
            entry = self._persist_message(event)
        elif isinstance(event, AgentEndEvent):
            # Aborted or exhausted turns must still release queued pair messages.
            self._open_tool_calls = 0
            self._flush_queued_pair_messages()
        await self._emit(event, signal)
        if entry is not None:
            await self._emit(EntryAppendedEvent(entry=entry), signal)

    async def _emit_agent_extension(self, event: AgentEvent) -> None:
        extension_event: ExtensionLifecycleEvent
        if isinstance(event, AgentStartEvent):
            self._extension_turn_index = 0
            extension_event = ExtensionAgentStartEvent()
        elif isinstance(event, AgentEndEvent):
            extension_event = ExtensionAgentEndEvent(messages=event.messages)
        elif isinstance(event, TurnStartEvent):
            extension_event = ExtensionTurnStartEvent(
                turn_index=self._extension_turn_index,
                timestamp=time.time_ns() // 1_000_000,
            )
        elif isinstance(event, TurnEndEvent):
            extension_event = ExtensionTurnEndEvent(
                turn_index=self._extension_turn_index,
                message=event.message,
                tool_results=event.tool_results,
            )
        elif isinstance(event, MessageStartEvent):
            extension_event = ExtensionMessageStartEvent(message=event.message)
        elif isinstance(event, MessageUpdateEvent):
            extension_event = ExtensionMessageUpdateEvent(
                message=event.message,
                assistant_message_event=event.assistant_message_event,
            )
        elif isinstance(event, MessageEndEvent):
            extension_event = ExtensionMessageEndEvent(message=event.message)
        elif isinstance(event, ToolExecutionStartEvent):
            extension_event = ExtensionToolExecutionStartEvent(
                tool_call_id=event.tool_call_id,
                tool_name=event.tool_name,
                args=event.args,
            )
        elif isinstance(event, ToolExecutionUpdateEvent):
            extension_event = ExtensionToolExecutionUpdateEvent(
                tool_call_id=event.tool_call_id,
                tool_name=event.tool_name,
                args=event.args,
                partial_result=event.partial_result,
            )
        else:
            extension_event = ExtensionToolExecutionEndEvent(
                tool_call_id=event.tool_call_id,
                tool_name=event.tool_name,
                result=event.result,
                is_error=event.is_error,
            )
        await self._emit_extension(extension_event)
        if isinstance(event, TurnEndEvent):
            self._extension_turn_index += 1

    async def _emit_extension(self, event: ExtensionLifecycleEvent) -> None:
        await self.services.extensions.emit(event)

    async def _emit(self, event: AgentSessionEvent, signal: asyncio.Event) -> None:
        for listener in tuple(self._listeners):
            result = listener(event, signal)
            if inspect.isawaitable(result):
                await result

    def _persist_message(self, event: MessageEndEvent) -> MessageEntry | None:
        message = event.message
        if not isinstance(message, UserMessage | AssistantMessage | ToolResultMessage):
            return None
        entry = MessageEntry(
            type="message",
            id=self._entry_id_factory(),
            parent_id=self.session_manager.leaf_id,
            timestamp=self._timestamp_factory(),
            message=dump_message(message),
        )
        self.session_manager.append(entry)
        if isinstance(message, AssistantMessage):
            self._open_tool_calls += sum(
                1 for block in message.content if isinstance(block, ToolCall)
            )
        elif isinstance(message, ToolResultMessage):
            self._open_tool_calls = max(0, self._open_tool_calls - 1)
            if self._open_tool_calls == 0:
                self._flush_queued_pair_messages()
        return entry

    def _ensure_open(self) -> None:
        if self._closed:
            raise AgentSessionClosedError("AgentSession is closed")

    def _retryable_error(self) -> str | None:
        if not self.agent.state.messages:
            return None
        message = self.agent.state.messages[-1]
        if not isinstance(message, AssistantMessage) or not is_retryable_assistant_error(message):
            return None
        return message.error_message or "provider turn failed"

    async def _wait_for_retry(self, delay: float) -> bool:
        async def sleep_once() -> None:
            await self._sleep(delay)

        async def wait_for_cancel() -> None:
            await self._retry_cancel.wait()

        sleep_task = asyncio.create_task(sleep_once())
        cancel_task = asyncio.create_task(wait_for_cancel())
        try:
            done, _pending = await asyncio.wait(
                (sleep_task, cancel_task), return_when=asyncio.FIRST_COMPLETED
            )
            if cancel_task in done:
                return True
            await sleep_task
            return False
        finally:
            for task in (sleep_task, cancel_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(sleep_task, cancel_task, return_exceptions=True)

    async def _compact_for_overflow(self) -> bool:
        try:
            await self.compact(reason="overflow")
        except (SessionOperationCancelled, ValueError):
            return False
        return True

    async def _check_threshold_compaction(self, message: AssistantMessage) -> None:
        """Compact once when the finished turn's context exceeds the token threshold."""
        if not self._auto_compaction_enabled or self._compaction_service is None:
            return
        if message.stop_reason != "stop":
            return
        model = self.agent.state.model
        tokens = self._context_tokens(message)
        if tokens is None or tokens <= model.context_window - self._compaction_reserve_tokens:
            return
        try:
            await self.compact(reason="threshold")
        except (SessionOperationCancelled, ValueError):
            return

    def _context_tokens(self, message: AssistantMessage) -> int | None:
        usage = message.usage
        total = usage.total_tokens or (
            usage.input + usage.output + usage.cache_read + usage.cache_write
        )
        if total > 0:
            return total
        path = self.session_manager.active_path()
        if not path:
            return None
        return sum(self._compaction_token_count(entry) for entry in path)

    def _restore_active_context(self) -> None:
        leaf_id = self.session_manager.leaf_id
        if leaf_id is None:
            self.agent.restore_messages(())
            return
        context = project_session_context(SessionTree.build(self.session_manager.entries), leaf_id)
        self.agent.restore_messages(context.messages)


def _extension_values(outcomes: Sequence[object]) -> tuple[object, ...]:
    return tuple(
        value for outcome in outcomes if (value := getattr(outcome, "value", None)) is not None
    )


def _cancelled(values: Sequence[object]) -> bool:
    return any(
        isinstance(value, Mapping) and cast("Mapping[str, object]", value).get("cancel") is True
        for value in values
    )


def _nested_mapping(values: Sequence[object], key: str) -> Mapping[str, object] | None:
    for value in values:
        if not isinstance(value, Mapping):
            continue
        nested = cast("Mapping[str, object]", value).get(key)
        if isinstance(nested, Mapping):
            return cast("Mapping[str, object]", nested)
    return None


__all__ = [
    "AgentSession",
    "AgentSessionClosedError",
    "SessionOperationCancelled",
]
