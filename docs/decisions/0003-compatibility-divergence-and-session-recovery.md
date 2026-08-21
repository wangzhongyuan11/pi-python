# ADR 0003：兼容状态、必要分歧与 Session 恢复

- 状态：Accepted
- 日期：2026-08-15
- 决策者：Pi Python 重写项目

## 背景

“类似 Pi”不足以指导实现。我们需要逐项说明是否兼容，以及在 Python、安全和恢复语义上何时允许不同。最危险的含糊点是 Session 崩溃恢复：工具可能已经产生副作用，但 ToolResult 尚未落盘，系统无法仅凭 JSONL 判断工具是否执行过。

## 决策

### 兼容状态

- `Supported`：Python 1.0 对外提供该表面，成功路径、wire 字段和可观察语义与冻结源码兼容。内部实现可以是 Python 惯用设计。
- `Intentional divergence`：Python 1.0 明确提供不同语义或拒绝该行为；必须写明原因、迁移方式和测试。
- `Post-v1`：1.0 不实现；不得用 stub、静默降级或“部分支持”冒充实现。

每个 surface matrix 条目只能有且只有一个状态。新增公开表面前必须先更新矩阵。

### 通用兼容规则

- Python API 使用 `snake_case`；JSON、RPC、Session 和配置 wire 使用 alias 保持冻结源码的 `camelCase`。
- discriminated union 的判别值、事件顺序和 stop reason 原样保持。
- 未知的可扩展数据字段在合法 v3 entry 的 `details`/`data` 中保留；未知 entry `type` 不静默接纳。
- Python typed exception 代替随处抛出的通用 `Error`，但 CLI/RPC/stream 边界仍映射为已冻结的公开结果。

### 1.0 的有意分歧

1. 命令与配置根分别是 `pi-python`、`~/.pi-python/agent` 和 `.pi-python/`；上游 `.pi/` 只在显式兼容模式中只读访问。
2. 只内建 DeepSeek；其他 Provider 通过 Python Extension 注册。无内建 OAuth 或通用 credential store。
3. API key 不持久化到 `auth.json`；只从本次 CLI、进程环境或明确的 `.env` 文件解析。
4. 不加载或执行 JS/TS Extension。npm Pi Package 只允许提取纯数据资源，且安装流程不得执行 lifecycle scripts。
5. v3 Session 采用严格解析：任一非空 malformed JSON 行、无效 header、重复 id、未知 type、断链或字段类型错误都拒绝打开，原文件字节保持不变。冻结源码会跳过 malformed 行，因此这是安全分歧。
6. CLI 参数/用法错误退出 `2`；冻结源码多数路径退出 `1`。运行错误仍退出 `1`。
7. Extension 修改工具参数后重新进行 schema 校验；冻结源码明确不重新校验。
8. project trust 前不加载项目 context、prompt、skill、theme、settings 或 extension；纯文本 prompt 也视为不可信输入。
9. Provider credential 不传入 Coding Tool 子进程环境；若用户确实需要，必须在命令中显式提供。
10. macOS 以清晰错误拒绝，不做“可能可用”的未验证承诺。

### 崩溃与未配对 Tool Call 恢复

恢复时只检查当前活动分支：

1. 找出 AssistantMessage 中的每个 `toolCall.id`。
2. 若后续存在同 id 的 ToolResult，则已配对，不处理。
3. 若没有 ToolResult，追加一个确定性的 `ToolResultMessage`：相同 `toolCallId`/`toolName`、`isError=true`，content 是唯一固定英文文本 `Tool execution state is unknown after session recovery; the tool was not replayed.`。
4. 恢复过程**绝不执行工具**，也不猜测工具是否已经产生副作用。
5. 每次启动先重新扫描；已有恢复结果即视为配对，因此重复启动不会再次补写。
6. 只有完整通过 v3 严格校验的 Session 才允许补写；损坏文件保持只读失败。

该规则提供“恢复不重放副作用”和“补写结果幂等”，不提供工具副作用的 exactly-once 保证。若进程在工具完成后、ToolResult 落盘前崩溃，外部副作用可能已经发生。

## 源码证据

- 上游 v3 parser 对 malformed 行选择跳过：`D:\pi\packages\coding-agent\src\core\session-manager.ts:L299-L313,L488-L505 @ e14afc648`。
- 上游 tree reader 将孤儿 entry 当作 root：`D:\pi\packages\coding-agent\src\core\session-manager.ts:L1301-L1341 @ e14afc648`。
- 工具结果由 `toolCallId` 配对，并在工具完成后构造：`D:\pi\packages\agent\src\agent-loop.ts:L777-L795 @ e14afc648`。
- 工具异常、未知工具和参数验证错误会变成 error ToolResult：`D:\pi\packages\agent\src\agent-loop.ts:L600-L665,L670-L708 @ e14afc648`。
- 截断的 tool call 不会执行：`D:\pi\packages\agent\src\agent-loop.ts:L375-L406 @ e14afc648`。
- 上游 Extension 允许 `tool_call` handler 原地修改 input 且不再校验：`D:\pi\packages\coding-agent\src\core\extensions\types.ts:L899-L904 @ e14afc648`。
- 上游凭据既可临时 overlay，也可写入 `auth.json`：`D:\pi\packages\coding-agent\src\core\runtime-credentials.ts:L4-L31`、`packages\coding-agent\src\core\auth-storage.ts:L27-L38 @ e14afc648`。

## 结果

- 好处：兼容承诺可自动检查；崩溃恢复不会偷偷重复执行写文件、shell 或外部 API。
- 代价：某些上游可容忍的手工编辑 Session 会被拒绝；跨实现配置路径不能透明混用。
- 迁移：`.pi` 和上游 v3 通过显式只读检查/导入命令迁移；任何导入先写到新路径，不原地改写来源。
