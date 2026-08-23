"""Agent-core boundary for the Pi Python distribution."""

from importlib.metadata import version as _distribution_version

from .agent import Agent
from .context import AgentContext, ConvertToLlm, TransformContext, build_llm_context
from .events import (
    AgentEndEvent,
    AgentEvent,
    AgentEventSequence,
    AgentStartEvent,
    MessageEndEvent,
    MessageStartEvent,
    MessageUpdateEvent,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
    ToolExecutionUpdateEvent,
    TurnEndEvent,
    TurnStartEvent,
)
from .listeners import AgentEventListener
from .loop import AgentEventSink, AgentLoopConfig, PendingMessageSource, run_agent_loop
from .messages import (
    BRANCH_SUMMARY_PREFIX,
    BRANCH_SUMMARY_SUFFIX,
    COMPACTION_SUMMARY_PREFIX,
    COMPACTION_SUMMARY_SUFFIX,
    AgentMessage,
    BashExecutionMessage,
    BranchSummaryMessage,
    CompactionSummaryMessage,
    CustomMessage,
    bash_execution_to_text,
    default_convert_to_llm,
)
from .queues import QueueMode
from .state import AgentState
from .stream_function import set_default_stream_function
from .tool_pipeline import (
    AfterToolCallContext,
    AfterToolCallHook,
    AfterToolCallResult,
    BeforeToolCallContext,
    BeforeToolCallHook,
    BeforeToolCallResult,
    ToolCallOutcome,
    ToolEventSink,
    execute_tool_call,
    fail_tool_call,
)
from .tools import (
    AgentTool,
    AgentToolExecute,
    AgentToolResult,
    AgentToolUpdateCallback,
    PrepareArguments,
    ToolExecutionMode,
)

__version__ = _distribution_version("pi-python")

__all__ = [
    "AfterToolCallContext",
    "AfterToolCallHook",
    "AfterToolCallResult",
    "Agent",
    "AgentContext",
    "AgentEndEvent",
    "AgentEvent",
    "AgentEventListener",
    "AgentEventSequence",
    "AgentEventSink",
    "AgentLoopConfig",
    "AgentMessage",
    "AgentStartEvent",
    "AgentState",
    "AgentTool",
    "AgentToolExecute",
    "AgentToolResult",
    "AgentToolUpdateCallback",
    "BRANCH_SUMMARY_PREFIX",
    "BRANCH_SUMMARY_SUFFIX",
    "BashExecutionMessage",
    "BeforeToolCallContext",
    "BeforeToolCallHook",
    "BeforeToolCallResult",
    "BranchSummaryMessage",
    "COMPACTION_SUMMARY_PREFIX",
    "COMPACTION_SUMMARY_SUFFIX",
    "CompactionSummaryMessage",
    "ConvertToLlm",
    "CustomMessage",
    "MessageEndEvent",
    "MessageStartEvent",
    "MessageUpdateEvent",
    "PendingMessageSource",
    "PrepareArguments",
    "QueueMode",
    "ToolCallOutcome",
    "ToolEventSink",
    "ToolExecutionEndEvent",
    "ToolExecutionMode",
    "ToolExecutionStartEvent",
    "ToolExecutionUpdateEvent",
    "TransformContext",
    "TurnEndEvent",
    "TurnStartEvent",
    "__version__",
    "bash_execution_to_text",
    "build_llm_context",
    "default_convert_to_llm",
    "execute_tool_call",
    "fail_tool_call",
    "run_agent_loop",
    "set_default_stream_function",
]
