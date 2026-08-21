# Message、Event 与 Tool 契约

> 适用版本：Python 1.0；上游基线：`e14afc648`。本文件冻结领域对象、wire 字段和事件顺序，不规定内部类的具体实现。

## 1. 序列化约定

- Python 对象使用 `snake_case`；JSON/RPC/Session 使用 Pydantic alias 输出上游 `camelCase`。
- 每个 union 都有固定判别字段：content 用 `type`，message 用 `role`，event 用 `type`。
- Unix 消息时间戳是毫秒整数；Session entry 自身时间戳是 ISO 8601 字符串。
- 未声明的核心 Message/Content/RPC 字段在输入边界拒绝；明确的扩展载荷 `details`、`data` 可保留任意 JSON 值。已知 v3 Session entry 的顶层 extra 字段是兼容例外，按 Session 契约原样保留。
- Message/Event/Tool 对象不得携带 API key、Authorization header 或异常 traceback。

## 2. Content 与 Usage

| 类型 | 必填字段 | 可选字段 | 用途 |
|---|---|---|---|
| `text` | `type="text"`, `text: str` | `textSignature` | 用户/助手/工具文本 |
| `thinking` | `type="thinking"`, `thinking: str` | `thinkingSignature`, `redacted` | 助手推理块 |
| `image` | `type="image"`, `data: base64 str`, `mimeType: str` | 无 | 用户输入或工具结果图片 |
| `toolCall` | `type="toolCall"`, `id`, `name`, `arguments: object` | `thoughtSignature`, `namespace` | 助手请求工具 |

`Usage` 必填 `input`、`output`、`cacheRead`、`cacheWrite`、`totalTokens` 和 `cost`；`cost` 必填 `input`、`output`、`cacheRead`、`cacheWrite`、`total`。`reasoning` 是 output 的可选子集，不能再次计入 total；`cacheWrite1h` 是 cacheWrite 的可选子集。

源码证据：`D:\pi\packages\ai\src\types.ts:L332-L370,L370-L393 @ e14afc648`。

## 3. Message

### UserMessage

```json
{
  "role": "user",
  "content": "string or [text|image]",
  "timestamp": 0
}
```

### AssistantMessage

必填：

- `role="assistant"`
- `content: [text|thinking|toolCall]`
- `api`, `provider`, `model`
- `usage`
- `stopReason`
- `timestamp`

可选：`responseModel`、`responseId`、`diagnostics`、`deferred`、`errorMessage`、`rawStopReason`、`endTurn`。

`stopReason` 的 wire 值固定为：`pending | stop | length | toolUse | error | aborted | deferred`。

### ToolResultMessage

必填：

- `role="toolResult"`
- `toolCallId` 与 `toolName`
- `content: [text|image]`
- `isError: bool`
- `timestamp`

可选：`details`、工具自身 `usage`、`addedToolNames`。工具 usage 不进入主 LLM context 计费。

源码证据：`D:\pi\packages\ai\src\types.ts:L393-L455 @ e14afc648`。

## 4. Context、Model 与消息分层

`pi_ai.Context` 只包含 Provider 能理解的 `Message[]`、可选 system prompt 和 `Tool[]`。`pi_agent.AgentMessage` 可以由产品层扩展；每次 Provider 调用前必须先执行：

```text
AgentMessage[]
-> transform_context(AgentMessage[])
-> convert_to_llm(AgentMessage[])
-> pi_ai.Context.messages: Message[]
```

UI-only 消息由 `convert_to_llm()` 过滤。两个转换 hook 不得抛出普通运行错误；调用方应返回原值或安全 fallback。Context 的 tools 是当前请求可见工具快照，不是全局 registry 的可变引用。

源码证据：`D:\pi\packages\agent\src\types.ts:L149-L213,L316-L325,L412-L425 @ e14afc648`。

## 5. Provider 流事件

`AssistantMessageEvent` 精确包含 12 个判别值：

| 事件 | 必填载荷 |
|---|---|
| `start` | `partial` |
| `text_start` | `contentIndex`, `partial` |
| `text_delta` | `contentIndex`, `delta`, `partial` |
| `text_end` | `contentIndex`, `content`, `partial` |
| `thinking_start` | `contentIndex`, `partial` |
| `thinking_delta` | `contentIndex`, `delta`, `partial` |
| `thinking_end` | `contentIndex`, `content`, `partial` |
| `toolcall_start` | `contentIndex`, `partial` |
| `toolcall_delta` | `contentIndex`, `delta`, `partial` |
| `toolcall_end` | `contentIndex`, `toolCall`, `partial` |
| `done` | `reason=stop|length|toolUse|deferred`, `message` |
| `error` | `reason=aborted|error`, `error` |

顺序不变量：

1. 每个流恰好一个 `start`，且在任何 content update 之前。
2. 每个 content index 的 `*_start` 在其 delta 之前，`*_end` 在其 delta 之后。
3. 流恰好以一个 `done` 或 `error` 终止；终止后不得再发事件。
4. `partial.content` 随事件单调累积；最终事件中的 Message 是权威结果。
5. request/model/runtime 失败不从 stream function 抛出；它们编码为终止 `error` 事件。编程错误与不变量破坏仍可抛出。

源码证据：`D:\pi\packages\ai\src\types.ts:L509-L539`、`D:\pi\packages\agent\src\types.ts:L17-L27 @ e14afc648`。

## 6. Agent Event

| 层级 | 事件 |
|---|---|
| Agent | `agent_start`, `agent_end` |
| Turn | `turn_start`, `turn_end` |
| Message | `message_start`, `message_update`, `message_end` |
| Tool | `tool_execution_start`, `tool_execution_update`, `tool_execution_end` |

`message_update` 只用于流式 AssistantMessage，并携带原始 `assistantMessageEvent`。`turn_end` 携带本轮最终 AssistantMessage 和按模型调用顺序排列的 ToolResultMessage。`agent_end` 是本次运行最后一个 AgentEvent；Agent 只有在所有被 await 的 listener 完成后才算 idle。

源码证据：`D:\pi\packages\agent\src\types.ts:L428-L443 @ e14afc648`。

## 7. Tool 定义与流水线

基础 Tool 必填 `name`、`description`、JSON schema `parameters`；AgentTool 另外必填 `label` 和异步 `execute()`，可选 `prepareArguments()` 与 `executionMode`。

```python
class AgentTool(Protocol[ParamsT, DetailsT]):
    name: str
    label: str
    description: str
    parameters: dict[str, object]
    execution_mode: Literal["sequential", "parallel"] | None

    def prepare_arguments(self, raw: object) -> ParamsT: ...

    async def execute(
        self,
        tool_call_id: str,
        params: ParamsT,
        signal: AbortSignal | None,
        on_update: Callable[[AgentToolResult[DetailsT]], None] | None,
    ) -> AgentToolResult[DetailsT]: ...
```

调用顺序固定为：

```text
lookup
-> prepare_arguments
-> schema/Pydantic validation
-> before_tool_call
-> execute (may update)
-> after_tool_call
-> tool_execution_end
-> ToolResultMessage message_start/message_end
```

语义：

- 未知工具、参数非法、before hook 阻止、abort 和执行异常都转换为 `ToolResultMessage(isError=true)`；它们不是 Agent 进程崩溃。
- `after_tool_call` 对 `content/details/usage/isError/terminate` 是字段级替换，不做深合并。
- update callback 只在 `execute()` 尚未结束时有效；迟到 update 必须丢弃。
- `length` 终止的 AssistantMessage 中所有 tool call 都不得执行，应各自产生 error ToolResult。
- parallel 模式下准备/hook 按模型顺序执行；允许的工具并发执行；`tool_execution_end` 可按完成顺序出现，但持久化的 ToolResult 与 message events 必须按原 tool call 顺序出现。
- 只有批次内每个最终结果都 `terminate=true` 时才提前终止整个批次循环。

源码证据：`D:\pi\packages\agent\src\types.ts:L361-L410`、`D:\pi\packages\agent\src\agent-loop.ts:L409-L555,L582-L795 @ e14afc648`。

## 8. 最小事件序列

无工具成功：

```text
agent_start -> turn_start
-> message_start(user) -> message_end(user)
-> message_start(assistant) -> message_update* -> message_end(assistant)
-> turn_end -> agent_end
```

该起始顺序由 `D:\pi\packages\agent\src\agent-loop.ts:L95-L116 @ e14afc648` 直接定义；continue 路径同样先发 `agent_start -> turn_start`（同文件 `L120-L142`）。

一次工具调用：

```text
... assistant message_end
-> tool_execution_start -> tool_execution_update* -> tool_execution_end
-> message_start(toolResult) -> message_end(toolResult)
-> turn_end
-> turn_start -> next assistant ... -> agent_end
```

## 9. 必测断言

- 所有 Message/Content/Usage/Event 的 alias round-trip。
- 12 种 Provider event 的合法与非法序列。
- text、thinking、单/多 tool call、error、abort、length。
- 未知工具、参数非法、before block、execute throw、after override/throw。
- parallel 完成乱序但 ToolResult 按源顺序。
- execute settle 后 update 不污染下一轮。
- transform 在 convert 之前，UI-only AgentMessage 不进入 Provider Context。
