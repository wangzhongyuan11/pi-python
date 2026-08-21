# Python 1.0 Surface Matrix

> 基线：`D:\pi @ e14afc648e10fb6c527ea88fa627091ada764306`（Pi `0.84.1`）
> 状态定义：[ADR 0003](../decisions/0003-compatibility-divergence-and-session-recovery.md)

## 读法与 owner

每一行是一个可独立验收的兼容单元。`状态` 列只允许以下三个值：`Supported`、`Intentional divergence`、`Post-v1`。组合行会完整列出该 family 的所有成员；它们共享同一个状态、owner 和验收阶段。

| Owner | 责任 |
|---|---|
| `pi_ai` | Message/Model/Provider/stream/codec |
| `pi_agent` | Agent state、event、loop、tool dispatch |
| `pi_tui` | 通用终端组件与通用 action |
| `pi_coding_agent.cli` | CLI、输出模式、bootstrap |
| `pi_coding_agent.session` | SessionManager、runtime、recovery |
| `pi_coding_agent.tools` | 七个 coding tool 与 operations |
| `pi_coding_agent.resources` | Settings、trust、resource/package discovery |
| `pi_coding_agent.extensions` | Python Extension API/runtime |
| `pi_coding_agent.rpc` | 本地 JSONL RPC/client |
| `pi_coding_agent.tui` | Agent-aware 交互 TUI |
| `pi_coding_agent` | 跨包 composition、平台门与 release 验证 |

## 1. CLI flags 与输入

| ID | 上游表面 | 状态 | Python 语义/边界 | 源码证据 | Python owner / phase |
|---|---|---|---|---|---|
| `CLI-FLAG-001` | positional `[messages...]` | Supported | TUI 初始消息或 print prompt | `packages/coding-agent/src/cli/args.ts:L229-L230` | `pi_coding_agent.cli` / P6,P12 |
| `CLI-FLAG-002` | `@files...` | Supported | 文本/图片附件；RPC 模式拒绝 | `packages/coding-agent/src/cli/args.ts:L211-L212`; `packages/coding-agent/src/main.ts:L646-L649` | `pi_coding_agent.cli` / P12 |
| `CLI-FLAG-003` | `--help`, `-h` | Supported | 显示静态与 Extension 动态 flags | `packages/coding-agent/src/cli/args.ts:L77-L80,L237-L308` | `pi_coding_agent.cli` / P6,P12 |
| `CLI-FLAG-004` | `--version`, `-v` | Supported | 输出 Python distribution 版本 | `packages/coding-agent/src/cli/args.ts:L79-L80`; `packages/coding-agent/src/main.ts:L621-L624` | `pi_coding_agent.cli` / P6 |
| `CLI-FLAG-005` | `--mode text\|json\|rpc` | Supported | 本地三模式；rpc 是 stdin/stdout JSONL | `packages/coding-agent/src/cli/args.ts:L81-L85` | `pi_coding_agent.cli` / P6,P12 |
| `CLI-FLAG-006` | `--print`, `-p` | Supported | 非交互处理后退出 | `packages/coding-agent/src/cli/args.ts:L143-L149` | `pi_coding_agent.cli` / P6 |
| `CLI-FLAG-007` | `--provider <name>` | Supported | 内建 `deepseek`；其他名称需 Python Extension | `packages/coding-agent/src/cli/args.ts:L90-L91` | `pi_coding_agent.cli` / P4,P10 |
| `CLI-FLAG-008` | `--model <pattern>` | Supported | 支持 `provider/id` 与 `:<thinking>` 解析 | `packages/coding-agent/src/cli/args.ts:L92-L93`; `packages/coding-agent/src/main.ts:L468-L519` | `pi_coding_agent.cli` / P4,P12 |
| `CLI-FLAG-009` | `--api-key <key>` | Supported | 仅本次运行，绝不持久化；优先级见 paths contract | `packages/coding-agent/src/cli/args.ts:L94-L95` | `pi_coding_agent.cli` / P4 |
| `CLI-FLAG-010` | `--system-prompt <text>` | Supported | 替换 base system prompt | `packages/coding-agent/src/cli/args.ts:L96-L97` | `pi_coding_agent.resources` / P7 |
| `CLI-FLAG-011` | `--append-system-prompt <text>` | Supported | 可重复；参数既可文本也可文件内容 | `packages/coding-agent/src/cli/args.ts:L98-L100` | `pi_coding_agent.resources` / P7 |
| `CLI-FLAG-012` | `--thinking <level>` | Supported | `off\|minimal\|low\|medium\|high\|xhigh\|max`，按模型能力 clamp | `packages/coding-agent/src/cli/args.ts:L60-L64,L133-L142`; `packages/coding-agent/src/core/sdk.ts:L226-L244` | `pi_coding_agent.cli` / P4,P6 |
| `CLI-FLAG-013` | `--continue`, `-c` | Supported | 继续当前 cwd 最近 Session | `packages/coding-agent/src/cli/args.ts:L86-L87` | `pi_coding_agent.session` / P3,P6 |
| `CLI-FLAG-014` | `--resume`, `-r` | Supported | 交互选择 Session | `packages/coding-agent/src/cli/args.ts:L88-L89` | `pi_coding_agent.session` / P6,P11 |
| `CLI-FLAG-015` | `--session <path\|id>` | Supported | 路径、精确/部分 id；跨项目显式 fork | `packages/coding-agent/src/cli/args.ts:L109-L110`; `packages/coding-agent/src/main.ts:L393-L415` | `pi_coding_agent.session` / P3,P6 |
| `CLI-FLAG-016` | `--session-id <id>` | Supported | 精确 id，存在则打开，否则创建；严格命名校验 | `packages/coding-agent/src/cli/args.ts:L111-L112`; `packages/coding-agent/src/main.ts:L317-L338,L438-L450` | `pi_coding_agent.session` / P3,P6 |
| `CLI-FLAG-017` | `--fork <path\|id>` | Supported | 复制完整来源历史到新 v3 Session | `packages/coding-agent/src/cli/args.ts:L113-L114`; `packages/coding-agent/src/main.ts:L301-L315,L350-L390` | `pi_coding_agent.session` / P3,P6 |
| `CLI-FLAG-018` | `--session-dir <dir>` | Supported | CLI > env > settings > 默认 encoded cwd | `packages/coding-agent/src/cli/args.ts:L115-L116`; `packages/coding-agent/src/main.ts:L677-L682` | `pi_coding_agent.session` / P3,P6 |
| `CLI-FLAG-019` | `--no-session` | Supported | 全内存 Session | `packages/coding-agent/src/cli/args.ts:L107-L108` | `pi_coding_agent.session` / P3 |
| `CLI-FLAG-020` | `--name`, `-n <name>` | Supported | append `session_info`；换行清理、空值拒绝 | `packages/coding-agent/src/cli/args.ts:L101-L106`; `packages/coding-agent/src/core/session-manager.ts:L1136-L1160` | `pi_coding_agent.session` / P3 |
| `CLI-FLAG-021` | `--models <patterns>` | Supported | 模型循环 scope，逗号分隔 | `packages/coding-agent/src/cli/args.ts:L117-L118` | `pi_coding_agent.cli` / P4,P11 |
| `CLI-FLAG-022` | `--no-tools`, `-nt` | Supported | 禁用内建、Extension 与 custom tools | `packages/coding-agent/src/cli/args.ts:L119-L120` | `pi_coding_agent.tools` / P5,P12 |
| `CLI-FLAG-023` | `--no-builtin-tools`, `-nbt` | Supported | 只禁用七个内建工具 | `packages/coding-agent/src/cli/args.ts:L121-L122` | `pi_coding_agent.tools` / P5,P12 |
| `CLI-FLAG-024` | `--tools`, `-t <names>` | Supported | 所有工具的 allowlist | `packages/coding-agent/src/cli/args.ts:L123-L127` | `pi_coding_agent.tools` / P5,P12 |
| `CLI-FLAG-025` | `--exclude-tools`, `-xt <names>` | Supported | 所有工具的 denylist；deny 优先 | `packages/coding-agent/src/cli/args.ts:L128-L132` | `pi_coding_agent.tools` / P5,P12 |
| `CLI-FLAG-026` | `--extension`, `-e <path>` | Supported | 仅加载 Python Extension；可重复 | `packages/coding-agent/src/cli/args.ts:L152-L154` | `pi_coding_agent.extensions` / P10 |
| `CLI-FLAG-027` | `--no-extensions`, `-ne` | Supported | 停止 discovery；显式 `-e` 仍加载 | `packages/coding-agent/src/cli/args.ts:L155-L156` | `pi_coding_agent.extensions` / P10 |
| `CLI-FLAG-028` | `--skill <path>` | Supported | 可重复的临时 Skill 来源 | `packages/coding-agent/src/cli/args.ts:L157-L159` | `pi_coding_agent.resources` / P7 |
| `CLI-FLAG-029` | `--no-skills`, `-ns` | Supported | 禁止 discovery | `packages/coding-agent/src/cli/args.ts:L174-L175` | `pi_coding_agent.resources` / P7 |
| `CLI-FLAG-030` | `--prompt-template <path>` | Supported | 可重复的临时 Prompt 来源 | `packages/coding-agent/src/cli/args.ts:L160-L162` | `pi_coding_agent.resources` / P7 |
| `CLI-FLAG-031` | `--no-prompt-templates`, `-np` | Supported | 禁止 discovery | `packages/coding-agent/src/cli/args.ts:L176-L177` | `pi_coding_agent.resources` / P7 |
| `CLI-FLAG-032` | `--theme <path>` | Supported | 可重复的临时 Theme 来源 | `packages/coding-agent/src/cli/args.ts:L163-L165` | `pi_coding_agent.resources` / P7,P11 |
| `CLI-FLAG-033` | `--use-theme <name>` | Supported | 本次运行初始 theme | `packages/coding-agent/src/cli/args.ts:L166-L173` | `pi_coding_agent.tui` / P11 |
| `CLI-FLAG-034` | `--no-themes` | Supported | 禁止 theme discovery | `packages/coding-agent/src/cli/args.ts:L178-L179` | `pi_coding_agent.resources` / P7 |
| `CLI-FLAG-035` | `--no-context-files`, `-nc` | Supported | 禁止 AGENTS/CLAUDE context discovery | `packages/coding-agent/src/cli/args.ts:L180-L181` | `pi_coding_agent.resources` / P7 |
| `CLI-FLAG-036` | `--export <file> [output]` | Supported | 安全 HTML export 后退出 | `packages/coding-agent/src/cli/args.ts:L150-L151`; `packages/coding-agent/src/main.ts:L626-L638` | `pi_coding_agent.session` / P12 |
| `CLI-FLAG-037` | `--list-models [search]` | Supported | 列出 DeepSeek 与已注册 Extension models | `packages/coding-agent/src/cli/args.ts:L182-L188` | `pi_coding_agent.cli` / P4,P12 |
| `CLI-FLAG-038` | `--tui-mode regular\|fullscreen` | Supported | prompt_toolkit 两种模式，非逐像素兼容 | `packages/coding-agent/src/cli/args.ts:L189-L202` | `pi_coding_agent.tui` / P9,P11 |
| `CLI-FLAG-039` | `--verbose` | Supported | 覆盖 quiet startup | `packages/coding-agent/src/cli/args.ts:L203-L204` | `pi_coding_agent.cli` / P12 |
| `CLI-FLAG-040` | `--approve`, `-a` | Supported | 仅信任本次 project resources；不是逐工具批准 | `packages/coding-agent/src/cli/args.ts:L205-L206`; `packages/coding-agent/src/core/project-trust.ts:L46-L49` | `pi_coding_agent.resources` / P7 |
| `CLI-FLAG-041` | `--no-approve`, `-na` | Supported | 本次忽略 project resources | `packages/coding-agent/src/cli/args.ts:L207-L208` | `pi_coding_agent.resources` / P7 |
| `CLI-FLAG-042` | `--offline` | Supported | 禁止启动网络刷新/安装；Provider 请求仍仅在用户 prompt 时发生 | `packages/coding-agent/src/cli/args.ts:L209-L210` | `pi_coding_agent.cli` / P12 |
| `CLI-FLAG-043` | Extension dynamic `--flag[=value]` | Supported | 两阶段解析，boolean/string，冲突诊断 | `packages/coding-agent/src/cli/args.ts:L213-L226`; `packages/coding-agent/src/core/extensions/types.ts:L1272-L1282` | `pi_coding_agent.extensions` / P10 |
| `CLI-FLAG-044` | Python-only `--env-file <path>` | Intentional divergence | 安全读取单个 dotenv；上游无该 flag | 上游 Args 全表：`packages/coding-agent/src/cli/args.ts:L13-L58` | `pi_coding_agent.cli` / P4 |

## 2. CLI subcommands

| ID | 上游表面 | 状态 | Python 语义/边界 | 源码证据 | Python owner / phase |
|---|---|---|---|---|---|
| `CLI-CMD-001` | `install <source> [--local\|-l] [--approve\|-a\|--no-approve\|-na] [--help\|-h]` | Supported | local/Git/PyPI Python package；npm 仅纯数据、禁 scripts | `packages/coding-agent/src/package-manager-cli.ts:L189-L318,L682-L772`; Python 安全边界见 [ADR 0003](../decisions/0003-compatibility-divergence-and-session-recovery.md) | `pi_coding_agent.resources` / P10,P12 |
| `CLI-CMD-002` | `remove <source> [--local\|-l] [--approve\|-a\|--no-approve\|-na] [--help\|-h]` | Supported | 移除配置与托管资源 | `packages/coding-agent/src/package-manager-cli.ts:L189-L318,L773-L783` | `pi_coding_agent.resources` / P10,P12 |
| `CLI-CMD-003` | `uninstall` alias | Supported | `remove` 的精确 alias | `packages/coding-agent/src/package-manager-cli.ts:L192-L194` | `pi_coding_agent.resources` / P10,P12 |
| `CLI-CMD-004` | `update [source\|self\|pi]` 与 `--self\|--extensions\|--models\|--all\|--extension\|--force\|--approve\|-a\|--no-approve\|-na\|--help\|-h` | Supported | wheel 自更新给出安装器命令；packages/catalog 可更新 | `packages/coding-agent/src/package-manager-cli.ts:L232-L370,L820-L880` | `pi_coding_agent.resources` / P10,P12 |
| `CLI-CMD-005` | `list [--help\|-h]` | Supported | 列出 user/project package sources 与 resolved path | `packages/coding-agent/src/package-manager-cli.ts:L189-L318,L784-L819` | `pi_coding_agent.resources` / P10 |
| `CLI-CMD-006` | `config [--local\|-l] [--help\|-h]` | Supported | 可信后启停 package resources | `packages/coding-agent/src/package-manager-cli.ts:L609-L675` | `pi_coding_agent.resources` / P10,P11 |
| `CLI-CMD-007` | `auth check [--json] [--no-refresh]` | Supported | 只检查 DeepSeek/Extension provider readiness，不打印 key | `packages/coding-agent/src/cli/auth-command.ts:L38-L94` | `pi_coding_agent.cli` / P6,P12 |
| `CLI-CMD-008` | `auth print-api-key` | Supported | 仅用户显式调用该专用命令时把 key 写 stdout；不写 Session/log/stderr | `packages/coding-agent/src/cli/auth-command.ts:L47-L94`; `packages/coding-agent/src/main.ts:L182-L208` | `pi_coding_agent.cli` / P6,P12 |
| `CLI-CMD-009` | `auth print-bearer-token [--min-expiry]` | Intentional divergence | 无内建 OAuth/credential store | `packages/coding-agent/src/cli/auth-command.ts:L38-L94` | `pi_coding_agent.cli` / P12 |
| `CLI-CMD-010` | experimental `pi` / `server` / `client` commands | Post-v1 | 远程 CBOR Session 栈整体延后 | `packages/coding-agent/src/cli/experimental/cli.ts:L1-L7`; `packages/coding-agent/src/cli/experimental/commands/pi.ts:L13-L47`; `packages/server/package.json:L2-L4` | `pi_coding_agent.remote` / Post-v1 |
| `CLI-CMD-011` | `auth check --credentials` | Intentional divergence | 1.0 拒绝该选项；凭据只允许由显式 `auth print-api-key` 写 stdout | `packages/coding-agent/src/cli/auth-command.ts:L38-L44,L47-L94` | `pi_coding_agent.cli` / P6,P12 |
| `CLI-CMD-012` | Python-only `import-pi-session <source> [--session-dir <dir>]` | Intentional divergence | 只接受成熟 v3；只读来源并创建新的 `.pi-python` Session | `packages/coding-agent/src/core/session-manager.ts:L30-L156,L514-L555`; [Session v3 契约](../contracts/session-v3.md) | `pi_coding_agent.session` / P3,P6 |

## 3. SDK exports

本节逐个覆盖冻结 root `index.ts` 的公开 export block。只有同一 export block 且状态、owner、phase 完全相同的符号才保留为 family；`覆盖符号/边界` 列是该 family 的完整成员清单。

| ID | Export family | 状态 | 覆盖符号/边界 | 源码证据 | Python owner / phase |
|---|---|---|---|---|---|
| `SDK-001` | AI core root exports | Supported | 完整成员 family：`models`, `models-store`, `faux`, `types`, `diagnostics`, `event-stream`, `json-parse`, `overflow`, `retry`, `contentText`, `uuidv7`, `validation` | `packages/ai/src/index.ts:L34-L47`; `packages/ai/src/types.ts:L332-L539` | `pi_ai` / P1,P4 |
| `SDK-002` | AI TypeBox root exports | Intentional divergence | 完整成员：`Static`, `TSchema`, `Type`, `typebox-helpers`；Python 用 Pydantic v2 | `packages/ai/src/index.ts:L1-L2,L45` | `pi_ai` / P1 |
| `SDK-003` | AI provider API option/modules | Intentional divergence | 完整成员：Anthropic、Azure OpenAI、Bedrock、Google、Vertex、Mistral、OpenAI Codex/Completions/Responses、Pi Messages、`api/lazy`；仅 DeepSeek adapter 内部复用 OpenAI-compatible wire | `packages/ai/src/index.ts:L9-L20`; `packages/ai/src/providers/all.ts:L1-L155` | `pi_ai` / P4,P10 |
| `SDK-004` | AI auth/context/store/helpers/types | Intentional divergence | 完整成员为 `auth/context`, `auth/credential-store`, `auth/helpers`, `auth/types`；内核不持久化凭据 | `packages/ai/src/index.ts:L21-L24`; `packages/ai/package.json:L29-L41` | `pi_ai` / P4,P10 |
| `SDK-005` | AI image/session-resource APIs | Post-v1 | 完整成员：`images-models`, `session-resources`；1.0 仅保留消息附件契约 | `packages/ai/src/index.ts:L33,L37`; `packages/ai/src/types.ts:L457-L479` | `pi_ai.images` / Post-v1 |
| `SDK-006` | Agent telemetry root exports | Supported | 完整成员：`Telemetry`, `TelemetryContext`, `TelemetryEvent`, `TelemetryEventFor`, `TelemetryEventMap`, `TelemetryEventType`, `NoopTelemetry`, `InMemoryTelemetry` | `packages/agent/src/index.ts:L3-L42` | `pi_telemetry` / P1 |
| `SDK-007` | Agent core root exports | Supported | 完整成员：`agent`, `agent-loop`, `types`, `setDefaultStreamFn`；含 `Agent`, `runAgentLoop`, `AgentState`, `AgentEvent`, `AgentTool` | `packages/agent/src/index.ts:L43-L45,L143-L145`; `packages/agent/src/types.ts:L28-L443` | `pi_agent` / P2 |
| `SDK-008` | Agent Harness/session/testing exports | Post-v1 | 完整成员为 root Harness blocks、`./session`, `./session/testing`、operation/lanes/v4 repository helpers | `packages/agent/src/index.ts:L46-L138`; `packages/agent/package.json:L8-L21` | `pi_agent.harness` / Post-v1 |
| `SDK-009` | Agent proxy/search/node helpers | Post-v1 | 完整成员：`proxy`, `search/index`, package subpath `./node` | `packages/agent/src/index.ts:L139-L141`; `packages/agent/src/node.ts:L1-L2`; `packages/agent/package.json:L8-L21` | `pi_agent.node` / Post-v1 |
| `SDK-010` | Coding Args/config block | Supported | 完整成员：`Args`, `parseArgs`, `CONFIG_DIR_NAME`, `getAgentDir`, `getDocsPath`, `getExamplesPath`, `getPackageDir`, `getReadmePath`, `VERSION` | `packages/coding-agent/src/index.ts:L3-L14` | `pi_coding_agent.cli` / P6,P12 |
| `SDK-011` | Coding AgentSession block | Supported | 完整成员：`AgentSession`, `AgentSessionConfig`, `AgentSessionEvent`, `AgentSessionEventListener`, `ModelCycleResult`, `ParsedSkillBlock`, `PromptOptions`, `parseSkillBlock`, `SessionStats` | `packages/coding-agent/src/index.ts:L15-L25` | `pi_coding_agent.session` / P6,P8 |
| `SDK-012` | `readStoredCredential` | Intentional divergence | 不导出、不实现 core credential store；显式 `auth print-api-key` 是唯一受控 key stdout | `packages/coding-agent/src/index.ts:L26`; `packages/coding-agent/src/core/auth-storage.ts:L1-L40` | `pi_coding_agent.cli` / P4,P6 |
| `SDK-013` | Coding compaction block | Supported | 完整成员：`BranchPreparation`, `BranchSummaryResult`, `CollectEntriesResult`, `CompactionResult`, `CutPointResult`, `calculateContextTokens`, `collectEntriesForBranchSummary`, `compact`, `DEFAULT_COMPACTION_SETTINGS`, `estimateTokens`, `FileOperations`, `findCutPoint`, `findTurnStartIndex`, `GenerateBranchSummaryOptions`, `generateBranchSummary`, `generateSummary`, `generateSummaryWithUsage`, `getLastAssistantUsage`, `prepareBranchEntries`, `serializeConversation`, `shouldCompact` | `packages/coding-agent/src/index.ts:L27-L50` | `pi_coding_agent.compaction` / P8 |
| `SDK-014` | Coding EventBus block | Supported | 完整成员：`createEventBus`, `EventBus`, `EventBusController` | `packages/coding-agent/src/index.ts:L51` | `pi_coding_agent.extensions` / P10 |
| `SDK-015` | Coding Extension export block | Supported | 完整成员为 `Extension*`, lifecycle/provider/tool/input/session event types，以及 `createExtensionRuntime`, `defineTool`, `discoverAndLoadExtensions`, `ExtensionRunner`, 八个 result guards、`isToolCallEventType`, `wrapRegisteredTool(s)`；逐名清单即该唯一显式 export block | `packages/coding-agent/src/index.ts:L52-L167` | `pi_coding_agent.extensions` / P10,P11 |
| `SDK-016` | Footer/message/model blocks | Supported | 完整成员：`ReadonlyFooterDataProvider`, `convertToLlm`, `ModelRegistry`, `ModelScopeDiagnostic`, `ResolveCliModelResult`, `ResolveModelScopeResult`, `resolveCliModel`, `resolveModelScopeWithDiagnostics`, `ScopedModel`, `CreateModelRuntimeOptions`, `CredentialSynchronizationError`, `CredentialSynchronizationOperation`, `ModelRuntime`, `ModelRuntimeAuthOverrides` | `packages/coding-agent/src/index.ts:L168-L186` | `pi_coding_agent.session` / P4,P6 |
| `SDK-017` | Package/resource blocks | Supported | 完整成员：`PackageManager`, `PathMetadata`, `ProgressCallback`, `ProgressEvent`, `ResolvedPaths`, `ResolvedResource`, `DefaultPackageManager`, `ResourceCollision`, `ResourceDiagnostic`, `ResourceLoader`, `DefaultResourceLoader`, `loadProjectContextFiles` | `packages/coding-agent/src/index.ts:L187-L197` | `pi_coding_agent.resources` / P7,P10 |
| `SDK-018` | SDK runtime/factory block | Supported | 完整成员：`AgentSessionRuntime`, 七个 runtime/service option/result types, `createAgentSession`, `createAgentSessionFromServices`, `createAgentSessionRuntime`, `createAgentSessionServices`, 七个 tool factories, `createCodingTools`, `createReadOnlyTools`, `PromptTemplate` | `packages/coding-agent/src/index.ts:L198-L225` | `pi_coding_agent.session` / P5,P6 |
| `SDK-019` | SessionManager/v3 block | Supported | 完整成员：九类 v3 entry types、`FileEntry`, `SessionContext`, `SessionEntryBase`, `SessionHeader`, `SessionInfo`, `SessionManager`, `SessionTreeNode`, `CURRENT_SESSION_VERSION`, `buildContextEntries`, `buildSessionContext`, `getLatestCompactionEntry`, `migrateSessionEntries`, `parseSessionEntries`, `sessionEntryToContextMessages` | `packages/coding-agent/src/index.ts:L226-L251` | `pi_coding_agent.session` / P3,P8 |
| `SDK-020` | Settings block | Supported | 完整成员：`CompactionSettings`, `DefaultProjectTrust`, `FullscreenExitOutput`, `ImageSettings`, `PackageSource`, `RetrySettings`, `SettingsManager`, `SettingsManagerCreateOptions`, `TuiMode` | `packages/coding-agent/src/index.ts:L252-L262` | `pi_coding_agent.resources` / P3,P7 |
| `SDK-021` | Skills/source block | Supported | 完整成员：`formatSkillsForPrompt`, `LoadSkillsFromDirOptions`, `LoadSkillsResult`, `loadSkills`, `loadSkillsFromDir`, `Skill`, `SkillFrontmatter`, `createSyntheticSourceInfo` | `packages/coding-agent/src/index.ts:L263-L273` | `pi_coding_agent.resources` / P7 |
| `SDK-022` | Edit-diff block | Supported | 完整成员：`EditDiffResult`, `generateDiffString`, `generateUnifiedPatch` | `packages/coding-agent/src/index.ts:L274` | `pi_coding_agent.tools` / P5 |
| `SDK-023` | Coding tool operations block | Supported | 完整成员为 Bash/Edit/Find/Grep/Ls/Read/Write input/detail/options/operations types、七个 definition factories、`createLocalBashOperations`, truncation constants/helpers、`withFileMutationQueue` | `packages/coding-agent/src/index.ts:L276-L324` | `pi_coding_agent.tools` / P5 |
| `SDK-024` | Project trust block | Supported | 完整成员：`hasTrustRequiringProjectResources`, `ProjectTrustDecision`, `ProjectTrustStore`, `ProjectTrustStoreEntry`, `ProjectTrustUpdate` | `packages/coding-agent/src/index.ts:L325-L331` | `pi_coding_agent.resources` / P7 |
| `SDK-025` | Coding main block | Supported | 完整成员：`MainOptions`, `main` | `packages/coding-agent/src/index.ts:L332-L333` | `pi_coding_agent.cli` / P6,P12 |
| `SDK-026` | Print/interactive/local RPC modes block | Supported | 完整成员：`InteractiveMode`, `InteractiveModeOptions`, `JsonAgentSessionEvent`, `ModelInfo`, `PrintModeOptions`, `RpcClient`, `RpcClientOptions`, `RpcCommand`, `RpcEventListener`, `RpcExtensionUIRequest`, `RpcExtensionUIResponse`, `RpcResponse`, `RpcSessionState`, `runPrintMode`, `runRpcMode` | `packages/coding-agent/src/index.ts:L334-L351` | `pi_coding_agent.rpc` / P6,P9,P11,P12 |
| `SDK-027` | Agent-aware interactive components block | Supported | 完整成员为 `ArminComponent` 至 `VisualTruncateResult` 的显式组件 block，包括 Login/OAuth selector；它们是 UI adapter，不表示内建 OAuth store | `packages/coding-agent/src/index.ts:L352-L390` | `pi_coding_agent.tui` / P11 |
| `SDK-028` | Theme block | Supported | 完整成员：`getLanguageFromPath`, `getMarkdownTheme`, `getSelectListTheme`, `getSettingsListTheme`, `highlightCode`, `initTheme`, `Theme`, `ThemeColor` | `packages/coding-agent/src/index.ts:L391-L401` | `pi_coding_agent.tui` / P7,P11 |
| `SDK-029` | Coding utility block | Supported | 完整成员：`copyToClipboard`, `parseFrontmatter`, `stripFrontmatter`, `convertToPng`, `formatDimensionNote`, `ResizedImage`, `resizeImage`, `getShellConfig` | `packages/coding-agent/src/index.ts:L402-L408` | `pi_coding_agent.resources` / P5,P7,P11 |
| `SDK-030` | Python `import_pi_session()` / `ImportResult` | Intentional divergence | 公开同步导入服务；只读成熟 v3 来源，输出新 Session | `packages/coding-agent/src/core/session-manager.ts:L30-L156,L514-L555`; [Session v3 契约](../contracts/session-v3.md) | `pi_coding_agent.session` / P3,P6 |
| `SDK-031` | coding-agent `./client`, `pi-client`, `pi-server`, `pi-protocol` remote families | Post-v1 | 完整成员：RemoteSession/transcript、client `.`/`./unix`、server `.`/`./testing`/`./unix`、protocol root；不与 local JSONL RPC 混用 | `packages/coding-agent/package.json:L19-L23`; `packages/coding-agent/src/client/index.ts:L1-L15`; `packages/client/package.json:L2-L22`; `packages/server/package.json:L2-L23`; `packages/protocol/package.json:L2-L9` | `pi_coding_agent.remote` / Post-v1 |
| `SDK-032` | Generic `pi_tui` core exports | Supported | 完整成员：autocomplete、Box/loader/editor/HStack/Input/Markdown/select/settings/Text、editor/fuzzy/keys/keybindings/StdinBuffer/Terminal、TUI main/alt screen、非图片 utils；LaTeX 使用文本 fallback | `packages/tui/src/index.ts:L1-L16,L18-L87,L116-L147` | `pi_tui` / P9 |
| `SDK-033` | `pi_tui` terminal image exports | Intentional divergence | 完整成员：`Image`, terminal image cell/protocol/detection/rendering APIs；1.0 只显示附件占位/元数据 | `packages/tui/src/index.ts:L17,L88-L115` | `pi_tui` / P9,P11 |

## 4. Session v3 entries 与行为

| ID | 表面 | 状态 | Python 语义/边界 | 源码证据 | Python owner / phase |
|---|---|---|---|---|---|
| `SESSION-001` | Header `type=session, version=3, id, timestamp, cwd, parentSession?` | Supported | 首条唯一 Header | `packages/coding-agent/src/core/session-manager.ts:L30-L46` | `pi_coding_agent.session` / P3 |
| `SESSION-002` | base `id,parentId,timestamp` append-only tree | Supported | parent 必须指向更早 entry | `packages/coding-agent/src/core/session-manager.ts:L46-L52,L845-L855` | `pi_coding_agent.session` / P3 |
| `SESSION-003` | `message` | Supported | 保存 AgentMessage 并进入 context | `packages/coding-agent/src/core/session-manager.ts:L53-L57,L383-L397` | `pi_coding_agent.session` / P3 |
| `SESSION-004` | `thinking_level_change` | Supported | 恢复 thinking，不直接进 context | `packages/coding-agent/src/core/session-manager.ts:L58-L62,L362-L376` | `pi_coding_agent.session` / P3 |
| `SESSION-005` | `model_change` | Supported | 恢复 provider/model，不直接进 context | `packages/coding-agent/src/core/session-manager.ts:L63-L68,L362-L376` | `pi_coding_agent.session` / P3 |
| `SESSION-006` | `compaction` | Supported | 摘要 + first kept entry 投影 | `packages/coding-agent/src/core/session-manager.ts:L69-L81,L418-L457` | `pi_coding_agent.compaction` / P8 |
| `SESSION-007` | `branch_summary` | Supported | 摘要消息进入活动分支 context | `packages/coding-agent/src/core/session-manager.ts:L82-L95,L401-L406` | `pi_coding_agent.compaction` / P8 |
| `SESSION-008` | `custom` | Supported | Extension 状态，不进入 context | `packages/coding-agent/src/core/session-manager.ts:L97-L110,L383-L410` | `pi_coding_agent.extensions` / P3,P10 |
| `SESSION-009` | `custom_message` | Supported | content 进入 context；details 不进入 | `packages/coding-agent/src/core/session-manager.ts:L127-L143,L398-L404` | `pi_coding_agent.extensions` / P3,P10 |
| `SESSION-010` | `label` | Supported | append change，最后值生效 | `packages/coding-agent/src/core/session-manager.ts:L111-L117,L1232-L1249` | `pi_coding_agent.session` / P3 |
| `SESSION-011` | `session_info` | Supported | session display name，空值清除 | `packages/coding-agent/src/core/session-manager.ts:L118-L126,L1136-L1160` | `pi_coding_agent.session` / P3 |
| `SESSION-012` | branch/reset/tree/fork/list/context projection | Supported | family 完整成员：`getBranch`, `branch`, `resetLeaf`, `getTree`, `forkFrom`, `list`, `listAll`, `buildContextEntries`, `buildSessionContext`；不改历史，fork 新 Header | `packages/coding-agent/src/core/session-manager.ts:L418-L469,L1260-L1417,L1579-L1713` | `pi_coding_agent.session` / P3,P8 |
| `SESSION-013` | 普通新建持久化 Session 的第一条 assistant 前延迟创建 | Supported | 不含显式空 `--session` 路径和 fork；避免空/失败对话残留 | `packages/coding-agent/src/core/session-manager.ts:L930-L955,L1015-L1042,L1579-L1629` | `pi_coding_agent.session` / P3 |
| `SESSION-014` | malformed JSON 静默跳过 | Intentional divergence | 严格拒绝，原文件字节不变 | `packages/coding-agent/src/core/session-manager.ts:L299-L313,L503-L555` | `pi_coding_agent.session` / P3 |
| `SESSION-015` | orphan 当 tree root | Intentional divergence | 断链视为损坏 | `packages/coding-agent/src/core/session-manager.ts:L1301-L1341` | `pi_coding_agent.session` / P3 |
| `SESSION-016` | 未知 entry `type` | Intentional divergence | 明确拒绝；已知 entry 的顶层 extra 及 details/data 原样保留 | `packages/coding-agent/src/core/session-manager.ts:L144-L156,L299-L313,L958-L976` | `pi_coding_agent.session` / P3 |
| `SESSION-017` | unmatched Tool Call 恢复 | Intentional divergence | 补一次 error result，文本固定为 `Tool execution state is unknown after session recovery; the tool was not replayed.`；绝不重放 | 上游配对字段：`packages/ai/src/types.ts:L437-L454`; 构造：`packages/agent/src/agent-loop.ts:L777-L790` | `pi_coding_agent.session` / P6 |
| `SESSION-018` | v1 -> v2 -> v3 自动 migration | Post-v1 | 1.0 只接受合法 v3；显式导入提示 | `packages/coding-agent/src/core/session-manager.ts:L220-L297` | `pi_coding_agent.session` / Post-v1 |
| `SESSION-019` | Harness v4/SQLite Session | Post-v1 | 与本 v3 contract 分离 | `packages/agent/src/harness/session/index.ts:L1-L13`; `packages/session-backends/sqlite-node/src/index.ts:L1-L114` | `pi_agent.harness` / Post-v1 |
| `SESSION-020` | 成熟 v3 `.pi` -> 新 `.pi-python` Session import | Intentional divergence | 严格 v3、保留已知 entry extra、来源字节不变、原子创建新文件；不自动迁移 v1/v2 | `packages/coding-agent/src/core/session-manager.ts:L30-L156,L299-L313,L514-L555`; [Session v3 契约](../contracts/session-v3.md) | `pi_coding_agent.session` / P3,P6 |

## 5. Local JSONL RPC

| ID | RPC surface | 状态 | Python 语义/边界 | 源码证据 | Python owner / phase |
|---|---|---|---|---|---|
| `RPC-001` | `prompt`, `steer`, `follow_up`, `abort`, `new_session` | Supported | optional id correlation；prompt 可带 images/streamingBehavior | `packages/coding-agent/src/modes/rpc/rpc-types.ts:L20-L26` | `pi_coding_agent.rpc` / P12 |
| `RPC-002` | `get_state` | Supported | 返回 model/thinking/stream/queue/session/compaction state | `packages/coding-agent/src/modes/rpc/rpc-types.ts:L29,L95-L108` | `pi_coding_agent.rpc` / P12 |
| `RPC-003` | `set_model`, `cycle_model`, `get_available_models` | Supported | DeepSeek + Extension catalog | `packages/coding-agent/src/modes/rpc/rpc-types.ts:L32-L34` | `pi_coding_agent.rpc` / P12 |
| `RPC-004` | `set_thinking_level`, `cycle_thinking_level`, `get_available_thinking_levels` | Supported | 使用 wire thinking enum | `packages/coding-agent/src/modes/rpc/rpc-types.ts:L37-L39` | `pi_coding_agent.rpc` / P12 |
| `RPC-005` | `set_steering_mode`, `set_follow_up_mode` | Supported | `all\|one-at-a-time` | `packages/coding-agent/src/modes/rpc/rpc-types.ts:L42-L43` | `pi_coding_agent.rpc` / P12 |
| `RPC-006` | `compact`, `set_auto_compaction` | Supported | manual instructions + enable flag | `packages/coding-agent/src/modes/rpc/rpc-types.ts:L46-L47` | `pi_coding_agent.rpc` / P12 |
| `RPC-007` | `set_auto_retry`, `abort_retry` | Supported | 整轮 retry 控制 | `packages/coding-agent/src/modes/rpc/rpc-types.ts:L50-L51` | `pi_coding_agent.rpc` / P12 |
| `RPC-008` | `bash`, `abort_bash` | Supported | user bash；可排除 context | `packages/coding-agent/src/modes/rpc/rpc-types.ts:L54-L55` | `pi_coding_agent.rpc` / P12 |
| `RPC-009` | `get_session_stats`, `export_html`, `switch_session`, `fork`, `clone` | Supported | cwd-bound runtime 在 replace 后重建 | `packages/coding-agent/src/modes/rpc/rpc-types.ts:L58-L62` | `pi_coding_agent.rpc` / P12 |
| `RPC-010` | `get_fork_messages`, `get_entries`, `get_tree`, `get_last_assistant_text`, `set_session_name` | Supported | tree/entry response 保持 v3 alias | `packages/coding-agent/src/modes/rpc/rpc-types.ts:L63-L67` | `pi_coding_agent.rpc` / P12 |
| `RPC-011` | `get_messages`, `get_commands` | Supported | AgentMessage 与 slash command metadata | `packages/coding-agent/src/modes/rpc/rpc-types.ts:L70-L73` | `pi_coding_agent.rpc` / P12 |
| `RPC-012` | success/failure response union | Supported | `type=response, command, success, data/error` | `packages/coding-agent/src/modes/rpc/rpc-types.ts:L115-L231` | `pi_coding_agent.rpc` / P12 |
| `RPC-013` | AgentSession event frames | Supported | 与 response 共用 stdout，按事件发生顺序 | `packages/coding-agent/src/modes/rpc/rpc-mode.ts:L1-L12,L54-L71` | `pi_coding_agent.rpc` / P12 |
| `RPC-014` | Extension UI `select`, `confirm`, `input` | Supported | request id + response/cancel + timeout/abort | `packages/coding-agent/src/modes/rpc/rpc-types.ts:L238-L283`; `packages/coding-agent/src/modes/rpc/rpc-mode.ts:L90-L150` | `pi_coding_agent.rpc` / P12 |
| `RPC-015` | Extension UI `editor` | Supported | request id + response/cancel；不承诺 timeout | `packages/coding-agent/src/modes/rpc/rpc-types.ts:L238-L283`; `packages/coding-agent/src/modes/rpc/rpc-mode.ts:L254-L270` | `pi_coding_agent.rpc` / P12 |
| `RPC-016` | Extension UI `notify`, `setStatus`, `setWidget`, `setTitle`, `set_editor_text` | Supported | fire-and-forget event frames | `packages/coding-agent/src/modes/rpc/rpc-types.ts:L238-L283`; `packages/coding-agent/src/modes/rpc/rpc-mode.ts:L152-L161,L168-L176,L195-L225,L238-L245` | `pi_coding_agent.rpc` / P12 |
| `RPC-017` | strict LF JSONL framing | Supported | U+2028/U+2029 不分帧；EOF final record 可读 | `packages/coding-agent/src/modes/rpc/jsonl.ts:L4-L58` | `pi_coding_agent.rpc` / P12 |
| `RPC-018` | parse/command errors | Supported | failure response，协议进程继续；stdout 无日志 | `packages/coding-agent/src/modes/rpc/rpc-mode.ts:L748-L797` | `pi_coding_agent.rpc` / P12 |
| `RPC-019` | local stdin/stdout JSONL RPC in Python 1.0 | Supported | 本地 subprocess transport；与远程 CBOR 栈明确分离 | `packages/coding-agent/src/modes/rpc/rpc-mode.ts:L1-L12,L52-L62`; `packages/coding-agent/src/modes/rpc/jsonl.ts:L4-L58` | `pi_coding_agent.rpc` / P12 |
| `RPC-020` | framed CBOR remote protocol/client/server | Post-v1 | 完整 remote family 延后，不与 local JSONL RPC 混用 | `packages/protocol/package.json:L2-L9`; `packages/client/package.json:L2-L22`; `packages/server/package.json:L2-L23` | `pi_coding_agent.remote` / Post-v1 |

## 6. Extension API

| ID | Extension surface | 状态 | 覆盖/分歧 | 源码证据 | Python owner / phase |
|---|---|---|---|---|---|
| `EXT-001` | async/sync Extension factory 与 inline extension | Supported | Python callable；初始化可 await | `packages/coding-agent/src/core/extensions/types.ts:L1519-L1533` | `pi_coding_agent.extensions` / P10 |
| `EXT-002` | Event subscription：`project_trust, resources_discover, session_start, session_info_changed, session_before_switch, session_before_fork, session_before_compact, session_compact, session_shutdown, session_before_tree, session_tree` | Supported | before events 可 cancel/replace；shutdown 可 teardown | `packages/coding-agent/src/core/extensions/types.ts:L519-L668,L1203-L1219` | `pi_coding_agent.extensions` / P10 |
| `EXT-003` | Event subscription：`context, before_provider_request, before_provider_headers, after_provider_response, before_agent_start` | Supported | payload/header/context hooks；secrets redacted | `packages/coding-agent/src/core/extensions/types.ts:L670-L711,L1220-L1227` | `pi_coding_agent.extensions` / P10 |
| `EXT-004` | Event subscription：`agent_start, agent_end, agent_settled, turn_start, turn_end, message_start, message_update, message_end` | Supported | Agent lifecycle 与 replacement semantics | `packages/coding-agent/src/core/extensions/types.ts:L712-L760,L1228-L1235` | `pi_coding_agent.extensions` / P10 |
| `EXT-005` | Event subscription：`tool_execution_start, tool_execution_update, tool_execution_end, model_select, thinking_level_select, tool_call, tool_result, user_bash, input` | Supported | typed events/results | `packages/coding-agent/src/core/extensions/types.ts:L762-L1058,L1236-L1244` | `pi_coding_agent.extensions` / P10 |
| `EXT-006` | `registerTool` / ToolDefinition/renderers | Supported | Pydantic schema、stream update、execution mode、UI renderer | `packages/coding-agent/src/core/extensions/types.ts:L449-L509,L1249-L1255` | `pi_coding_agent.extensions` / P10,P11 |
| `EXT-007` | `registerCommand`, `registerShortcut`, `registerFlag`, `getFlag` | Supported | 动态 CLI/TUI surface | `packages/coding-agent/src/core/extensions/types.ts:L1175-L1191,L1260-L1282` | `pi_coding_agent.extensions` / P10 |
| `EXT-008` | `registerMessageRenderer`, `registerEntryRenderer`, `registerMarkdownTransformer` | Supported | Agent-aware TUI 与 HTML export adapter | `packages/coding-agent/src/core/extensions/types.ts:L1141-L1173,L1284-L1297` | `pi_coding_agent.extensions` / P10,P11 |
| `EXT-009` | actions：`sendMessage, sendUserMessage, appendEntry, set/getSessionName, setLabel, exec` | Supported | session append、队列、shell result | `packages/coding-agent/src/core/extensions/types.ts:L1300-L1335` | `pi_coding_agent.extensions` / P10 |
| `EXT-010` | actions：`getActiveTools, getAllTools, setActiveTools, getCommands` | Supported | source metadata 与 dynamic refresh | `packages/coding-agent/src/core/extensions/types.ts:L1337-L1347` | `pi_coding_agent.extensions` / P10 |
| `EXT-011` | actions：`setModel, get/setThinkingLevel` | Supported | clamp 能力、credential readiness | `packages/coding-agent/src/core/extensions/types.ts:L1349-L1360` | `pi_coding_agent.extensions` / P10 |
| `EXT-012` | context：idle/trust/signal/abort/pending/shutdown/usage/compact/system prompt | Supported | readonly sessionManager + controlled actions | `packages/coding-agent/src/core/extensions/types.ts:L307-L347` | `pi_coding_agent.extensions` / P10 |
| `EXT-013` | command context：wait/new/fork/navigate/switch/reload + replacement context | Supported | replacement 后 fresh cwd-bound context | `packages/coding-agent/src/core/extensions/types.ts:L353-L410` | `pi_coding_agent.extensions` / P10 |
| `EXT-014` | UI dialogs/input/notify/status/working/widget/footer/header/title/custom/editor/autocomplete/theme/tool expansion | Supported | prompt_toolkit components；RPC 支持其 wire subset | `packages/coding-agent/src/core/extensions/types.ts:L96-L281` | `pi_coding_agent.extensions` / P10,P11 |
| `EXT-015` | `registerProvider`/`unregisterProvider`/custom stream/models | Supported | Python Provider Protocol；立即生效/撤销 | `packages/coding-agent/src/core/extensions/types.ts:L1362-L1493` | `pi_coding_agent.extensions` / P10 |
| `EXT-016` | Extension-owned OAuth/persistent credentials | Intentional divergence | Extension 自己负责安全存储；Python 内核不提供上游 auth.json/AuthStorage | `packages/coding-agent/src/core/extensions/types.ts:L1470-L1491`; `packages/coding-agent/src/config.ts:L533-L536`; `packages/coding-agent/src/core/auth-storage.ts:L1-L40` | `pi_coding_agent.extensions` / P10 |
| `EXT-017` | shared EventBus | Supported | runtime invalidation 时自动退订 | `packages/coding-agent/src/core/extensions/types.ts:L1434-L1437,L1600-L1624`; `packages/coding-agent/src/core/extensions/loader.ts:L206-L224` | `pi_coding_agent.extensions` / P10 |
| `EXT-018` | handler failure isolation/ExtensionError | Supported | 捕获、诊断、不中断其他 extension；stack 不出 wire | `packages/coding-agent/src/core/extensions/types.ts:L1712-L1727`; `packages/coding-agent/src/core/extensions/runner.ts:L801-L832` | `pi_coding_agent.extensions` / P10 |
| `EXT-019` | tool_call 参数原地修改后“不重新校验” | Intentional divergence | Python 修改后重新 Pydantic 校验 | `packages/coding-agent/src/core/extensions/types.ts:L899-L904` | `pi_coding_agent.extensions` / P10 |
| `EXT-020` | JS/TS/Jiti Extension 执行 | Intentional divergence | 只执行 Python Extension | `packages/coding-agent/src/core/extensions/loader.ts:L1-L17,L436-L463,L490-L515`; `packages/coding-agent/package.json:L60` | `pi_coding_agent.extensions` / P10 |
| `EXT-021` | npm package executable code/lifecycle scripts | Intentional divergence | npm 只读取纯数据，使用 `pack --ignore-scripts` 等价安全流程 | 上游 npm install：`packages/coding-agent/src/core/package-manager.ts:L1758-L1784` | `pi_coding_agent.resources` / P10 |
| `EXT-022` | Node sidecar compatibility | Post-v1 | 不在 1.0 启动 Node | `packages/coding-agent/src/core/extensions/loader.ts:L1-L29,L436-L463` | `pi_coding_agent.extensions` / Post-v1 |

## 7. TUI actions

### 通用 `pi_tui` actions

| ID | Surface | 状态 | Python 语义/边界 | 源码证据 | Python owner / phase |
|---|---|---|---|---|---|
| `TUI-GENERIC-001` | editor vertical/history：`tui.editor.cursorUp`, `tui.editor.cursorDown`, `tui.editor.historyPrevious`, `tui.editor.historyNext` | Supported | action 名与默认/替代键 registry | `packages/tui/src/keybindings.ts:L7-L12,L71-L81` | `pi_tui` / P9 |
| `TUI-GENERIC-002` | editor horizontal/word/line/jump/page：`tui.editor.cursorLeft`, `tui.editor.cursorRight`, `tui.editor.cursorWordLeft`, `tui.editor.cursorWordRight`, `tui.editor.cursorLineStart`, `tui.editor.cursorLineEnd`, `tui.editor.jumpForward`, `tui.editor.jumpBackward`, `tui.editor.pageUp`, `tui.editor.pageDown` | Supported | action 名与默认/替代键 registry | `packages/tui/src/keybindings.ts:L13-L22,L82-L115` | `pi_tui` / P9 |
| `TUI-GENERIC-003` | editor mutation：`tui.editor.deleteCharBackward`, `tui.editor.deleteCharForward`, `tui.editor.deleteWordBackward`, `tui.editor.deleteWordForward`, `tui.editor.deleteToLineStart`, `tui.editor.deleteToLineEnd`, `tui.editor.yank`, `tui.editor.yankPop`, `tui.editor.undo` | Supported | action 名与默认/替代键 registry | `packages/tui/src/keybindings.ts:L23-L31,L116-L142` | `pi_tui` / P9 |
| `TUI-GENERIC-004` | input：`tui.input.newLine`, `tui.input.submit`, `tui.input.tab`, `tui.input.copy` | Supported | action 名与默认/替代键 registry | `packages/tui/src/keybindings.ts:L33-L36,L143-L146` | `pi_tui` / P9 |
| `TUI-GENERIC-005` | select：`tui.select.up`, `tui.select.down`, `tui.select.pageUp`, `tui.select.pageDown`, `tui.select.confirm`, `tui.select.cancel` | Supported | action 名与默认/替代键 registry | `packages/tui/src/keybindings.ts:L38-L43,L147-L158` | `pi_tui` / P9 |
| `TUI-GENERIC-006` | alternate screen：`tui.altScreen.pageUp`, `tui.altScreen.pageDown`, `tui.altScreen.halfPageUp`, `tui.altScreen.halfPageDown`, `tui.altScreen.lineUp`, `tui.altScreen.lineDown`, `tui.altScreen.previousPrompt`, `tui.altScreen.nextPrompt`, `tui.altScreen.search`, `tui.altScreen.searchNext`, `tui.altScreen.searchPrevious`, `tui.altScreen.searchClose`, `tui.altScreen.top`, `tui.altScreen.bottom` | Supported | action 名与默认/替代键 registry | `packages/tui/src/keybindings.ts:L45-L58,L159-L210` | `pi_tui` / P9 |

### Coding Agent app actions

| ID | Surface | 状态 | Python 语义/边界 | 源码证据 | Python owner / phase |
|---|---|---|---|---|---|
| `TUI-APP-001` | lifecycle：`app.interrupt`, `app.clear`, `app.exit`, `app.suspend` | Supported | action 名与默认/替代键 registry | `packages/coding-agent/src/core/keybindings.ts:L13-L17,L64-L72` | `pi_coding_agent.tui` / P11 |
| `TUI-APP-002` | model/thinking/tools：`app.thinking.cycle`, `app.model.cycleForward`, `app.model.cycleBackward`, `app.model.select`, `app.tools.expand`, `app.thinking.toggle` | Supported | action 名与默认/替代键 registry | `packages/coding-agent/src/core/keybindings.ts:L18-L23,L73-L90` | `pi_coding_agent.tui` / P11 |
| `TUI-APP-003` | editor/message/clipboard：`app.editor.external`, `app.message.copy`, `app.message.followUp`, `app.message.dequeue`, `app.clipboard.pasteImage` | Supported | action 名与默认/替代键 registry | `packages/coding-agent/src/core/keybindings.ts:L25-L29,L95-L114` | `pi_coding_agent.tui` / P11 |
| `TUI-APP-004` | Session commands：`app.session.toggleNamedFilter`, `app.session.new`, `app.session.tree`, `app.session.fork`, `app.session.resume`, `app.session.togglePath`, `app.session.toggleSort`, `app.session.rename`, `app.session.delete`, `app.session.deleteNoninvasive` | Supported | action 名与默认/替代键 registry | `packages/coding-agent/src/core/keybindings.ts:L24,L30-L33,L38-L42,L91-L94,L115-L118,L135-L154` | `pi_coding_agent.tui` / P11 |
| `TUI-APP-005` | tree navigation/label：`app.tree.foldOrUp`, `app.tree.unfoldOrDown`, `app.tree.editLabel`, `app.tree.toggleLabelTimestamp` | Supported | action 名与默认/替代键 registry | `packages/coding-agent/src/core/keybindings.ts:L34-L37,L119-L134` | `pi_coding_agent.tui` / P11 |
| `TUI-APP-006` | model scope editor：`app.models.save`, `app.models.enableAll`, `app.models.clearAll`, `app.models.toggleProvider`, `app.models.reorderUp`, `app.models.reorderDown` | Supported | action 名与默认/替代键 registry | `packages/coding-agent/src/core/keybindings.ts:L43-L48,L155-L178` | `pi_coding_agent.tui` / P11 |
| `TUI-APP-007` | tree filters：`app.tree.filter.default`, `app.tree.filter.noTools`, `app.tree.filter.userOnly`, `app.tree.filter.labeledOnly`, `app.tree.filter.all`, `app.tree.filter.cycleForward`, `app.tree.filter.cycleBackward` | Supported | action 名与默认/替代键 registry | `packages/coding-agent/src/core/keybindings.ts:L49-L55,L179-L206` | `pi_coding_agent.tui` / P11 |
| `TUI-APP-008` | legacy unnamespaced keybinding name migration | Supported | 配置加载时迁移，canonical 输出 namespaced key | `packages/coding-agent/src/core/keybindings.ts:L209-L269,L289-L326` | `pi_coding_agent.tui` / P9,P11 |

macOS 平台整体为 `Intentional divergence`，在启动时清晰拒绝；这不改变上述 action 在 Windows/Linux 的 `Supported` 状态。

## 8. Settings keys

| ID | Key | 状态 | Python 语义/边界 | 源码证据 | Python owner / phase |
|---|---|---|---|---|---|
| `SETTING-001` | `lastChangelogVersion` | Supported | update/changelog state | `packages/coding-agent/src/core/settings-manager.ts:L90-L93` | `pi_coding_agent.resources` / P12 |
| `SETTING-002` | `defaultProvider` | Supported | 默认 `deepseek` 或 Extension provider | `packages/coding-agent/src/core/settings-manager.ts:L92-L94` | `pi_coding_agent.resources` / P4,P7 |
| `SETTING-003` | `defaultModel` | Supported | DeepSeek model id/pattern | `packages/coding-agent/src/core/settings-manager.ts:L92-L95` | `pi_coding_agent.resources` / P4,P7 |
| `SETTING-004` | `defaultThinkingLevel` | Supported | thinking enum | `packages/coding-agent/src/core/settings-manager.ts:L93-L95` | `pi_coding_agent.resources` / P4,P7 |
| `SETTING-005` | `transport` | Intentional divergence | DeepSeek 只实现 SSE；`auto` 等价 SSE，websocket 值拒绝 | `packages/coding-agent/src/core/settings-manager.ts:L95`; `packages/ai/src/types.ts:L106` | `pi_ai` / P4 |
| `SETTING-006` | `steeringMode` | Supported | `all\|one-at-a-time` | `packages/coding-agent/src/core/settings-manager.ts:L96` | `pi_agent` / P2,P7 |
| `SETTING-007` | `followUpMode` | Supported | `all\|one-at-a-time` | `packages/coding-agent/src/core/settings-manager.ts:L97` | `pi_agent` / P2,P7 |
| `SETTING-008` | `theme` | Supported | theme name | `packages/coding-agent/src/core/settings-manager.ts:L98` | `pi_coding_agent.tui` / P7,P11 |
| `SETTING-009` | `compaction.enabled/reserveTokens/keepRecentTokens` | Supported | defaults `true/16384/20000` | `packages/coding-agent/src/core/settings-manager.ts:L12-L16,L99` | `pi_coding_agent.compaction` / P7,P8 |
| `SETTING-010` | `branchSummary.reserveTokens/skipPrompt` | Supported | defaults `16384/false` | `packages/coding-agent/src/core/settings-manager.ts:L18-L21,L100` | `pi_coding_agent.compaction` / P7,P8 |
| `SETTING-011` | `retry.enabled/maxRetries/baseDelayMs` | Supported | 整轮 retry，默认 `true/3/2000` | `packages/coding-agent/src/core/settings-manager.ts:L29-L34,L101` | `pi_coding_agent.session` / P7,P8 |
| `SETTING-012` | `retry.provider.timeoutMs/maxRetries/maxRetryDelayMs` | Supported | Provider 请求 retry 独立计数 | `packages/coding-agent/src/core/settings-manager.ts:L23-L27,L29-L34` | `pi_ai` / P4,P7 |
| `SETTING-013` | `hideThinkingBlock` | Supported | TUI visibility | `packages/coding-agent/src/core/settings-manager.ts:L102` | `pi_coding_agent.tui` / P11 |
| `SETTING-014` | `showCacheMissNotices` | Supported | DeepSeek/Provider 有数据时显示 | `packages/coding-agent/src/core/settings-manager.ts:L103` | `pi_coding_agent.tui` / P11 |
| `SETTING-015` | `externalEditor` | Supported | 覆盖 VISUAL/EDITOR | `packages/coding-agent/src/core/settings-manager.ts:L104` | `pi_coding_agent.tui` / P11 |
| `SETTING-016` | `shellPath` | Supported | Windows/Linux bash 路径，支持 `~` | `packages/coding-agent/src/core/settings-manager.ts:L105` | `pi_coding_agent.tools` / P5,P7 |
| `SETTING-017` | `quietStartup` | Supported | CLI/TUI startup verbosity | `packages/coding-agent/src/core/settings-manager.ts:L106` | `pi_coding_agent.cli` / P7,P12 |
| `SETTING-018` | `defaultProjectTrust` | Supported | global-only `ask\|always\|never` | `packages/coding-agent/src/core/settings-manager.ts:L69-L70,L107` | `pi_coding_agent.resources` / P7 |
| `SETTING-019` | `shellCommandPrefix` | Supported | 每条 bash 前缀；视为用户授权代码 | `packages/coding-agent/src/core/settings-manager.ts:L108` | `pi_coding_agent.tools` / P5,P7 |
| `SETTING-020` | `npmCommand` | Intentional divergence | 不以 npm install 执行 Extension；npm data adapter 使用固定安全命令 | `packages/coding-agent/src/core/settings-manager.ts:L109` | `pi_coding_agent.resources` / P10 |
| `SETTING-021` | `collapseChangelog` | Supported | update UI | `packages/coding-agent/src/core/settings-manager.ts:L110` | `pi_coding_agent.cli` / P12 |
| `SETTING-022` | `enableInstallTelemetry` | Post-v1 | 1.0 不发送安装 ping | `packages/coding-agent/src/core/settings-manager.ts:L111` | `pi_telemetry` / Post-v1 |
| `SETTING-023` | `enableAnalytics` | Post-v1 | 1.0 无远程 analytics | `packages/coding-agent/src/core/settings-manager.ts:L112` | `pi_telemetry` / Post-v1 |
| `SETTING-024` | `trackingId` | Post-v1 | 1.0 不生成远程 tracking id | `packages/coding-agent/src/core/settings-manager.ts:L113` | `pi_telemetry` / Post-v1 |
| `SETTING-025` | `packages` 与 object filters `autoload/extensions/skills/prompts/themes` | Supported | local/Git/PyPI Python；npm 纯数据；trust/lock | `packages/coding-agent/src/core/settings-manager.ts:L79-L89,L114` | `pi_coding_agent.resources` / P10 |
| `SETTING-026` | `extensions` | Supported | 本地 Python Extension paths | `packages/coding-agent/src/core/settings-manager.ts:L115` | `pi_coding_agent.extensions` / P10 |
| `SETTING-027` | `skills` | Supported | Skill paths | `packages/coding-agent/src/core/settings-manager.ts:L116` | `pi_coding_agent.resources` / P7 |
| `SETTING-028` | `prompts` | Supported | Prompt template paths | `packages/coding-agent/src/core/settings-manager.ts:L117` | `pi_coding_agent.resources` / P7 |
| `SETTING-029` | `themes` | Supported | Theme paths | `packages/coding-agent/src/core/settings-manager.ts:L118` | `pi_coding_agent.resources` / P7,P11 |
| `SETTING-030` | `enableSkillCommands` | Supported | 注册 `/skill:name` | `packages/coding-agent/src/core/settings-manager.ts:L119` | `pi_coding_agent.resources` / P7 |
| `SETTING-031` | `terminal.showImages/imageWidthCells` | Intentional divergence | 无 Kitty/iTerm 图片协议；只显示附件占位/元数据 | `packages/coding-agent/src/core/settings-manager.ts:L39-L43,L120` | `pi_coding_agent.tui` / P11 |
| `SETTING-032` | `terminal.clearOnShrink/showTerminalProgress` | Supported | prompt_toolkit renderer/OSC 可用时 | `packages/coding-agent/src/core/settings-manager.ts:L39-L43,L120` | `pi_tui` / P9 |
| `SETTING-033` | `images.autoResize/blockImages` | Supported | resize 或请求前明确禁止 | `packages/coding-agent/src/core/settings-manager.ts:L46-L49,L121` | `pi_coding_agent.resources` / P7,P11 |
| `SETTING-034` | `enabledModels` | Supported | 与 `--models` 同格式 | `packages/coding-agent/src/core/settings-manager.ts:L122` | `pi_coding_agent.resources` / P4,P7 |
| `SETTING-035` | `defaultTools` | Supported | 初始内建工具选择 | `packages/coding-agent/src/core/settings-manager.ts:L123` | `pi_coding_agent.tools` / P5,P7 |
| `SETTING-036` | `doubleEscapeAction` | Supported | `fork\|tree\|none` | `packages/coding-agent/src/core/settings-manager.ts:L124` | `pi_coding_agent.tui` / P11 |
| `SETTING-037` | `treeFilterMode` | Supported | `default\|no-tools\|user-only\|labeled-only\|all` | `packages/coding-agent/src/core/settings-manager.ts:L125` | `pi_coding_agent.tui` / P11 |
| `SETTING-038` | `thinkingBudgets.minimal/low/medium/high` | Supported | Provider 支持时映射 token budget | `packages/coding-agent/src/core/settings-manager.ts:L51-L56,L126` | `pi_ai` / P4,P7 |
| `SETTING-039` | `editorPaddingX` | Supported | 非负 cell padding | `packages/coding-agent/src/core/settings-manager.ts:L127` | `pi_tui` / P9 |
| `SETTING-040` | `outputPad` | Supported | `0\|1` | `packages/coding-agent/src/core/settings-manager.ts:L128` | `pi_tui` / P9 |
| `SETTING-041` | `autocompleteMaxVisible` | Supported | 默认 5 | `packages/coding-agent/src/core/settings-manager.ts:L129` | `pi_tui` / P9 |
| `SETTING-042` | `showHardwareCursor` | Supported | IME/hardware cursor | `packages/coding-agent/src/core/settings-manager.ts:L130` | `pi_tui` / P9 |
| `SETTING-043` | `markdown.codeBlockIndent/mermaid` | Supported | mermaid `off\|final\|streaming`；文本 fallback | `packages/coding-agent/src/core/settings-manager.ts:L58-L63,L131` | `pi_coding_agent.tui` / P11 |
| `SETTING-044` | `warnings.anthropicExtraUsage` | Post-v1 | Anthropic-specific 且无内建 Anthropic | `packages/coding-agent/src/core/settings-manager.ts:L65-L67,L132` | `pi_ai` / Post-v1 |
| `SETTING-045` | `sessionDir` | Supported | 同 `--session-dir` | `packages/coding-agent/src/core/settings-manager.ts:L133` | `pi_coding_agent.session` / P3,P7 |
| `SETTING-046` | `httpProxy` | Supported | Pi-managed HTTP clients | `packages/coding-agent/src/core/settings-manager.ts:L134` | `pi_ai` / P4,P7 |
| `SETTING-047` | `httpIdleTimeoutMs` | Supported | `0` 禁用 | `packages/coding-agent/src/core/settings-manager.ts:L135` | `pi_ai` / P4,P7 |
| `SETTING-048` | `websocketConnectTimeoutMs` | Intentional divergence | 1.0 无 Provider websocket；读取时给迁移错误 | `packages/coding-agent/src/core/settings-manager.ts:L136` | `pi_ai` / P4 |
| `SETTING-049` | `tuiMode` | Supported | `regular\|fullscreen` | `packages/coding-agent/src/core/settings-manager.ts:L36,L137` | `pi_tui` / P9 |
| `SETTING-050` | `fullscreenExitOutput` | Supported | `transcript\|resume-hint` | `packages/coding-agent/src/core/settings-manager.ts:L37,L138` | `pi_tui` / P9 |
| `SETTING-051` | `fullscreenScrollbar` | Supported | prompt_toolkit scroll view 映射 | `packages/coding-agent/src/core/settings-manager.ts:L139` | `pi_tui` / P9 |

## 9. Built-in tools

| ID | Tool | 状态 | 参数与关键语义 | 源码证据 | Python owner / phase |
|---|---|---|---|---|---|
| `TOOL-001` | `read` | Supported | `path`, optional 1-based `offset`,`limit`；文本 head truncation；附件图片契约 | `packages/coding-agent/src/core/tools/read.ts:L21-L25,L209-L229,L250-L322` | `pi_coding_agent.tools` / P5 |
| `TOOL-002` | `bash` | Supported | `command`, optional seconds `timeout`；stream updates；tail truncation + full temp output | `packages/coding-agent/src/core/tools/bash.ts:L28-L44,L322-L364,L399-L459` | `pi_coding_agent.tools` / P5 |
| `TOOL-003` | `edit` | Supported | `path`, non-empty `edits[{oldText,newText}]`；fuzzy-normalized 匹配必须唯一/不重叠；整批校验后单次写 | `packages/coding-agent/src/core/tools/edit.ts:L34-L54,L131-L135,L298-L365`; `packages/coding-agent/src/core/tools/edit-diff.ts:L305-L360` | `pi_coding_agent.tools` / P5 |
| `TOOL-004` | `write` | Supported | `path`,`content`；创建父目录并完整覆盖 | `packages/coding-agent/src/core/tools/write.ts:L15-L18,L187-L230` | `pi_coding_agent.tools` / P5 |
| `TOOL-005` | `grep` | Supported | `pattern,path?,glob?,ignoreCase?,literal?,context?,limit?`；rg、gitignore、head truncation | `packages/coding-agent/src/core/tools/grep.ts:L24-L44,L128-L145,L190-L226,L338-L365` | `pi_coding_agent.tools` / P5 |
| `TOOL-006` | `find` | Supported | `pattern,path?,limit?`；fd、gitignore、POSIX 相对输出 | `packages/coding-agent/src/core/tools/find.ts:L16-L35,L123-L140,L224-L267,L321-L350` | `pi_coding_agent.tools` / P5 |
| `TOOL-007` | `ls` | Supported | `path?,limit?`；字母排序、目录 `/`、dotfiles | `packages/coding-agent/src/core/tools/ls.ts:L14-L26,L100-L112,L129-L205` | `pi_coding_agent.tools` / P5 |
| `TOOL-008` | Tool allow/deny/default sets | Supported | 全集七个；coding 默认 read/bash/edit/write，readonly 为 read/grep/find/ls | `packages/coding-agent/src/core/tools/index.ts:L84-L186` | `pi_coding_agent.tools` / P5 |
| `TOOL-009` | Windows Bash default + optional PowerShell Extension | Intentional divergence | 核心工具名仍为 bash；PowerShell 是随包、默认关闭的 Python Extension | `packages/coding-agent/src/utils/shell.ts:L61-L119`; Python 决策见 [ADR 0003](../decisions/0003-compatibility-divergence-and-session-recovery.md) | `pi_coding_agent.tools` / P5,P10 |
| `TOOL-010` | 核心 sandbox/逐工具确认 | Intentional divergence | 与上游一样默认无 sandbox；可选 permission Extension 默认关闭；`--approve` 不是工具确认 | `packages/coding-agent/src/core/project-trust.ts:L46-L49`; `packages/coding-agent/src/core/tools/bash.ts:L322-L364` | `pi_coding_agent.extensions` / P10 |
| `TOOL-011` | Python canonical-path mutation queue 与 atomic replace | Intentional divergence | write/edit 对同一真实路径串行；落盘失败不留下部分目标文件 | `packages/coding-agent/src/core/tools/index.ts:L83-L186`; [ADR 0003](../decisions/0003-compatibility-divergence-and-session-recovery.md) | `pi_coding_agent.tools` / P5 |

## 10. 平台与发布边界

| ID | 表面 | 状态 | 边界 | 源码证据 | Python owner / phase |
|---|---|---|---|---|---|
| `PLATFORM-001` | Windows 10/11 + Python 3.12/3.13 | Supported | Python CI、真终端 smoke、subprocess/tree kill | `packages/coding-agent/src/utils/shell.ts:L24-L43,L61-L106,L176-L224`; `packages/coding-agent/src/core/keybindings.ts:L64-L72,L111-L114`; [ADR 0001](../decisions/0001-source-baseline-and-scope.md) | `pi_coding_agent` / P0,P13 |
| `PLATFORM-002` | Linux + Python 3.12/3.13 | Supported | Python CI 与仓库外 wheel smoke | `packages/coding-agent/src/utils/shell.ts:L45-L57,L61-L71,L109-L119,L198-L224`; [ADR 0001](../decisions/0001-source-baseline-and-scope.md) | `pi_coding_agent` / P0,P13 |
| `PLATFORM-003` | macOS | Intentional divergence | 启动即 `PlatformNotSupportedError` | `packages/tui/package.json:L10-L24`; `packages/coding-agent/src/core/keybindings.ts:L119-L125`; [ADR 0001](../decisions/0001-source-baseline-and-scope.md) | `pi_coding_agent.cli` / P6 |
| `PLATFORM-004` | console command `pi-python` 与 `.pi-python` roots | Intentional divergence | 不覆盖上游 `pi`/`.pi` | `packages/coding-agent/package.json:L6-L11` | `pi_coding_agent.cli` / P0,P6 |
