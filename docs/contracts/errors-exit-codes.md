# 错误、输出通道与退出码契约

## 1. 原则

- 预期的用户、配置、Provider、Session 和 Tool 失败必须在所属边界转换为稳定结果。
- 编程错误和框架不变量破坏不得伪装成 ToolResult；测试中直接失败，CLI 顶层只输出清理后的通用错误。
- text/JSON/RPC Agent 输出不得出现 traceback、日志、进度条、API key 或 Authorization header。唯一例外是用户显式调用专用 `auth print-api-key` 命令；该命令按契约只向 stdout 写 key 和换行。
- 所有面向用户的错误包含可操作的下一步；内部 exception 可以保留 cause，但默认不序列化 stack。

## 2. Python exception taxonomy

```text
PiError
├── CliUsageError
├── ConfigError
├── CredentialError
├── ProviderError
│   ├── ProviderAuthError
│   ├── ProviderRateLimitError
│   ├── ProviderTimeoutError
│   └── ProviderProtocolError
├── SessionError
│   ├── SessionNotFoundError
│   ├── SessionCorruptError
│   └── SessionConflictError
├── ResourceError
│   ├── ProjectNotTrustedError
│   └── ExtensionLoadError
└── PlatformNotSupportedError
```

每个 `PiError` 提供稳定的机器码 `code`、安全 `message` 和可选 `details`；不得在 `details` 放 credential、完整环境或任意异常 repr。

## 3. 边界映射

| 失败位置 | 对外结果 |
|---|---|
| Provider request/model/runtime | 终止 `AssistantMessageEvent(type="error")`；final AssistantMessage 的 `stopReason=error|aborted` |
| 用户取消 Provider/Agent | `aborted`，不自动 retry |
| 未知工具/参数非法/before block/执行异常/after hook 异常 | `ToolResultMessage(isError=true)`，Agent 继续由模型决定 |
| Session/config/resource/extension 启动失败 | typed exception；CLI/RPC 顶层映射 |
| CLI 语法或冲突参数 | `CliUsageError`，stderr usage 摘要，exit 2 |
| 内部 invariant | 测试抛出原异常；生产 CLI 记录安全诊断 id，stderr 通用错误，exit 1 |

Provider 和 Tool 的冻结源码依据分别是 `D:\pi\packages\agent\src\types.ts:L17-L27` 与 `D:\pi\packages\agent\src\agent-loop.ts:L600-L737 @ e14afc648`。

## 4. 退出码

| 码 | 含义 | 示例 |
|---:|---|---|
| `0` | 成功或用户在无错误状态取消选择 | help/version、成功回答、未选择 resume |
| `1` | 运行失败 | 配置损坏、无凭据、Provider 最终失败、Session 损坏、Extension 加载失败、工具外的未处理运行错误 |
| `2` | CLI 用法/参数错误 | 未知短参数、缺少 flag 值、互斥 flag、RPC 不允许 `@file` |
| `130` | 顶层收到 Ctrl+C/SIGINT 并中止 | 非交互请求被用户中断 |

`2` 是有意分歧：冻结 CLI 的多数参数错误使用 `1`（`D:\pi\packages\coding-agent\src\main.ts:L306-L357,L611-L649 @ e14afc648`）。冻结 auth check 另有 `0/1/2` readiness 语义（同文件 `L188-L212`）；Python `auth check` 将 readiness 写入结构化结果，CLI 仍用 `0=ready, 1=not ready, 2=invalid invocation/state`。

## 5. stdout / stderr

| 模式 | stdout | stderr |
|---|---|---|
| TUI | 终端 UI；退出恢复终端状态 | 启动前 fatal diagnostic |
| text/print | 最终文本与明确请求的命令输出 | warning/error/progress |
| JSON | 每行一个 `JsonAgentSessionEvent`；不得混入普通文本 | diagnostic |
| RPC | 只允许严格 JSONL response/event/extension UI frame | diagnostic；不得写协议内容 |
| `auth print-api-key` | 仅显式专用命令输出 API key 和一个换行 | error/diagnostic；不得重复 key |
| `auth print-bearer-token` | Python 1.0 无内建 OAuth，不输出 token | 安全错误 |

## 6. RPC error

成功 response：

```json
{"id":"optional","type":"response","command":"get_state","success":true,"data":{}}
```

失败 response：

```json
{"id":"optional","type":"response","command":"get_state","success":false,"error":"safe message"}
```

- 无法解析 JSON 时 `command="parse"` 且 id 缺失。
- 未知命令和 schema 错误也返回 failure response，不关闭进程。
- command handler 抛出的 typed error 只暴露安全 message。
- LF 是唯一 frame delimiter；字符串内 U+2028/U+2029 不是 delimiter。

源码证据：`D:\pi\packages\coding-agent\src\modes\rpc\rpc-mode.ts:L1-L71,L743-L797`、`packages\coding-agent\src\modes\rpc\jsonl.ts:L4-L51 @ e14afc648`。

## 7. Retry 与可观察性

- Provider SDK/request retry 与 AgentSession 整轮 retry 是两个独立计数器，分别记录 attempt、delay、终止原因。
- abort 不 retry；schema/protocol 错误不按网络瞬态错误 retry。
- error 文本不作为程序分支依据；代码使用 exception type / error code / event discriminator。
- log 使用结构化字段并统一 redaction；不得记录 prompt 全文作为默认错误上下文。

## 8. 必测断言

- 每个 exception 到 CLI code、RPC failure 和安全 message 的表驱动测试。
- stdout purity：text/JSON/RPC 模式注入 warning/extension failure 后仍无污染。
- secret corpus（CLI key、env key、`.env` key、Authorization header）不出现在普通 stdout/stderr/log/exception repr；唯一例外测试断言显式 `auth print-api-key` 的 stdout 精确等于 `<key>\n`，且 stderr/其他通道无 key。
- Provider error/abort 是终止流事件，不是 rejected iterator。
- Tool failure进入 ToolResult，编程 invariant 不进入 ToolResult。
- Ctrl+C 终止子进程树并返回 130；无迟到事件。
