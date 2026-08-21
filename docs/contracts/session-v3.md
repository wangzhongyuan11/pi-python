# Session v3 JSONL 契约

> 适用版本：Python 1.0；wire 兼容目标：冻结上游 Coding Agent 的同步 `SessionManager`，不是 Harness/v4 repository。

## 1. 文件与 Header

文件是 UTF-8、LF 分隔的 JSON Lines。第一条非空记录必须且只能是 Header：

```json
{
  "type": "session",
  "version": 3,
  "id": "019...",
  "timestamp": "2026-08-15T12:34:56.789Z",
  "cwd": "D:\\workspace",
  "parentSession": "optional absolute path"
}
```

规则：

- 新文件固定 `version: 3`；普通 entry 不增加 `version` 或 `schemaVersion`。
- Header `id` 是 session id；新实现使用 UUIDv7 字符串。
- `parentSession` 只表达 fork 来源，不参与活动树的 parent 链。
- Header 后不能再次出现 `type="session"`。

源码证据：`D:\pi\packages\coding-agent\src\core\session-manager.ts:L30-L46,L927-L944 @ e14afc648`。

## 2. Entry 基类与类型

每条普通 entry 必填：

```json
{
  "type": "...",
  "id": "8-hex-or-compatible-id",
  "parentId": "previous-entry-id-or-null",
  "timestamp": "ISO-8601"
}
```

| `type` | 附加字段 | 是否进入 LLM context | Python owner / phase |
|---|---|---|---|
| `message` | `message: AgentMessage` | 是 | `pi_coding_agent.session` / P3 |
| `thinking_level_change` | `thinkingLevel` | 否；恢复运行设置 | `pi_coding_agent.session` / P3 |
| `model_change` | `provider`, `modelId` | 否；恢复运行设置 | `pi_coding_agent.session` / P3 |
| `compaction` | `summary`, `firstKeptEntryId`, `tokensBefore`; 可选 `details`, `usage`, `fromHook` | 是，以摘要替代旧上下文 | `pi_coding_agent.compaction` / P8 |
| `branch_summary` | `fromId`, `summary`; 可选 `details`, `usage`, `fromHook` | 是 | `pi_coding_agent.compaction` / P8 |
| `custom` | `customType`; 可选 `data` | 否，仅扩展状态 | `pi_coding_agent.extensions` / P3/P10 |
| `custom_message` | `customType`, `content`, `display`; 可选 `details` | 是，转换为 custom AgentMessage | `pi_coding_agent.extensions` / P3/P10 |
| `label` | `targetId`; 可选 `label`，缺失/空表示清除 | 否 | `pi_coding_agent.session` / P3 |
| `session_info` | 可选 `name`，空表示清除 | 否 | `pi_coding_agent.session` / P3 |

源码证据：`D:\pi\packages\coding-agent\src\core\session-manager.ts:L46-L156 @ e14afc648`。

## 3. 树与活动分支

- `id` 在文件内唯一。
- `parentId=null` 表示 root；非空 parent 必须引用文件中更早出现的普通 entry。
- Session append-only；已有记录不得修改或删除。
- manager 持有一个内存 `leaf_id`。append 创建当前 leaf 的 child 并推进 leaf；branch 只移动 leaf，不改历史。
- 打开文件时默认 leaf 是最后一条普通 entry；显式 tree navigation 可在内存中选择其他 leaf。
- 活动分支是从 leaf 沿 parent 回溯到 root 后反转的路径。
- label 是事件记录；目标显示标签取活动文件中对该 target 的最后一次 label change。

源码证据：`D:\pi\packages\coding-agent\src\core\session-manager.ts:L845-L855,L1198-L1285,L1290-L1404 @ e14afc648`。

## 4. Context 投影

普通 `custom`、label、session_info、model/thinking change 不直接成为消息。投影规则：

- `message` 原样输出；历史 message 的 null/missing content 仅在显式兼容导入器中规范为 `[]`，新 Python 写入不允许 null。
- `custom_message` 转为 custom AgentMessage。
- `branch_summary` 转为 branch summary message。
- 最新活动 compaction entry 成为 compaction summary；其前只保留从 `firstKeptEntryId` 到 compaction 之前的路径，其后保留所有活动路径 entry。
- thinking level 与 model 从完整活动路径恢复；AssistantMessage 的 provider/model 也更新恢复模型。

源码证据：`D:\pi\packages\coding-agent\src\core\session-manager.ts:L346-L468 @ e14afc648`。

## 5. 持久化

- 新 Session 在内存中先创建 Header；持久化模式只有出现第一条 AssistantMessage 后才创建文件并一次写入此前完整记录。
- 文件存在后，每个新 entry 追加一行；不得重写旧 entry。
- 创建使用 exclusive create，避免覆盖同名文件。
- 需要整文件输出的 fork/import/migration 写到同目录临时文件，flush/fsync 后原子 rename；源文件不原地修改。
- Session 文件权限目标为 POSIX `0600`、目录 `0700`；Windows 使用当前用户 ACL 的最佳可用实现。
- 文件名：`<timestamp-with-colons-and-dots-replaced-by-hyphens>_<session-id>.jsonl`。

上游延迟创建证据：`D:\pi\packages\coding-agent\src\core\session-manager.ts:L1008-L1042,L1478-L1494 @ e14afc648`。

## 6. 严格读取与兼容导入

正常 `open/resume/list`：

- 任一非空行 JSON 解析失败、无效 UTF-8、非法 Header、重复 id、未知 type、字段类型错误、断链、自指 parent 或 compaction 引用失效，抛出 `SessionCorruptError`。
- 已知 entry `type` 的顶层未知字段使用 `extra="allow"` 保留并原样 round-trip；这不等于接受未知 `type`。
- 失败不修改文件，不返回“看似可用”的部分 Session。
- `list` 可以把损坏文件报告为 diagnostic 并继续列出其他文件，但不能把它当成合法 Session。

显式 `import-pi-session`：

- 只读读取 `.pi` 来源；输出到 `.pi-python` 新文件。
- 可接受已知 v3 Header/entry 的额外未知字段并 round-trip 保留。
- v1/v2 自动迁移是 `Post-v1`；1.0 对旧版本给出明确错误与迁移提示。

冻结的公开入口：

- CLI：`pi-python import-pi-session <source> [--session-dir <dir>]`。
- SDK：`import_pi_session(source: str | Path, *, session_dir: str | Path | None = None) -> ImportResult`。
- `ImportResult` 至少包含 `session_id`、绝对 `session_file` 和绝对 `source_file`；CLI 成功时只把结果路径写 stdout，诊断写 stderr。
- 默认目标目录按来源 v3 Header 的 `cwd` 映射到 `.pi-python` Session root；显式 `--session-dir`/`session_dir` 覆盖它。
- Header id、timestamp、cwd、parentSession、普通 entries 和所有保留的 extra 字段不改写；目标使用 exclusive create，若同名目标已存在则明确失败，不覆盖。

这是相对冻结源码的有意分歧；上游会跳过 malformed 行并在 tree view 把 orphan 当 root。证据：`D:\pi\packages\coding-agent\src\core\session-manager.ts:L299-L313,L488-L523,L1301-L1341 @ e14afc648`。

## 7. 未配对 Tool Call 恢复

严格解析成功后，在活动分支扫描 AssistantMessage tool call 与后续 ToolResult：

- 已有相同 `toolCallId` 的 ToolResult：不处理。
- 未配对：按 tool call 源顺序追加 error ToolResult，保留原 `toolCallId`/`toolName`，并将 content 固定为唯一英文文本 `Tool execution state is unknown after session recovery; the tool was not replayed.`。
- 该固定文本表示上次运行可能已产生副作用；用户应检查外部状态后决定下一步。
- 补写后再启动不会重复追加，因为 tool call 已配对。
- 恢复绝不调用 Tool registry 或执行 Extension hook。

完整理由见 [ADR 0003](../decisions/0003-compatibility-divergence-and-session-recovery.md)。

## 8. Session id 与路径

显式 session id 必须匹配：

```regex
^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$
```

禁止路径分隔符、前后标点和空字符串。源码证据：`D:\pi\packages\coding-agent\src\core\session-manager.ts:L212-L219 @ e14afc648`。

## 9. 必测断言

- 九类 entry 的 TS -> Python -> TS JSONL round-trip。
- append 不改变任何旧字节；branch 只新增 child。
- delayed creation：只有 user message 时磁盘无文件，第一条 assistant 后一次出现完整前缀。
- compaction/context/model/thinking 恢复。
- duplicate id、orphan、unknown type、truncated last line、malformed middle line、invalid UTF-8 全部失败且文件 hash 不变。
- 合法 extra/details/data 字段保留。
- unmatched tool call 补一次 error result，连续恢复不重复且执行计数为零。
- fork 使用新 Header/session id/cwd/parentSession，来源文件 hash 不变。
