# 上游差距分析:Pi 1.1.0 与 Oh My Pi 18.10.1 vs pi-python

> 分析日期:2026-10-10。数据来源:
> - 上游最新发布 tarball `@earendil-works/pi-coding-agent@1.1.0`(2026-10-07)
> - Oh My Pi tarball `@oh-my-pi/pi-coding-agent@18.10.1`(can1357/oh-my-pi 分发版)
> - 冻结基线 `D:\pi @ e14afc648`(0.84.1,2026-08-14)
> - 本仓库 `src/` @ main `f3f969b`
>
> 证据等级标注:✅=已核实源码;推断=按模块名/规模判断,未逐行核实。

## 0. 三方总览

| | Pi 1.1.0(上游) | Oh My Pi 18.10.1(分发版) | pi-python(本项目) |
|---|---|---|---|
| 谱系 | 官方 monorepo | 第三方 fork(独立版本线 18.x) | 从零 Python 重写,行为基线 0.84.1 |
| 规模 | coding-agent:169 个 core 模块 + 4 个内建扩展 | src:1407 文件 / 494,509 行 TS,80+ 顶层模块 | 201 文件 / 27,189 行 Python(另有 954 测试) |
| 形态 | `pi` CLI,多 Provider,内建 MCP | `omp` CLI,pi 超集 + 大量自营能力 | `pi-python` CLI/TUI/SDK/RPC,DeepSeek 单 Provider |
| 语言 | TypeScript(dist 交付) | TypeScript(交付 src+dist) | Python |

## 1. Pi 1.1.0 相对基线(0.84.1)的新增,逐模块对照

### 1.1 新增 core 模块(9 个)

| 新模块 | 功能(✅ 已核实) | pi-python 现状 | 差距 |
|---|---|---|---|
| `core/mcp-servers` + `extensions/mcp` | 内建 MCP 客户端:`mcp__server__tool` 命名、`--no-mcp`、`--tools 'mcp__x__*'` 模式、OAuth 登录(超时/取消/端口回退)、`/mcp` 实时管理 | ❌ 无(Phase 18 计划中) | **大**。上游以"内建扩展 + core 配置模块"形态交付,且有成熟 OAuth 生命周期;P18 设计时应对齐(命名约定、`--no-mcp`、tool 模式匹配) |
| `extensions/codemode` | JS 运行时内程序化调用工具(`pi.tools.read()` 等),支持图片回传、输出分帧、`models.classify()` 分类器 | ❌ 无 | **大**。这是上游 1.x 的旗舰能力;依赖 `nested-tool-calls` |
| `core/nested-tool-calls` | 工具执行中的子工具调用(`ctx.executeTool()`):走完整工具管线、带 `parentToolCallId`、usage 归账到外层调用 | ❌ 无 | **中**。codemode/MCP 复合场景的地基 |
| `extensions/tool-search` | 工具目录搜索(按需暴露,配合 MCP 大目录) | 部分:Phase 18-T04 计划(deferred tools) | 中 |
| `extensions/llama` | llama.cpp 本地分类器模型接入 | ❌ 无(单 Provider divergence) | ➖ 不追 |
| `core/session-export` | 会话导出数据层(0.85+ 新增) | ✅ P17-T03 已有 HTML 导出(`export/html.py` + 投影) | 小:数据层形态不同,格式扩展时再对齐 |
| `core/cache-warmer` | prompt cache 预热 | ❌ 无 | 小(DeepSeek cache 语义不同,低优先) |
| `core/crash-log`、`core/bug-report(+upload)` | 崩溃日志与 bug 上报 | ❌ 无(crash-log 低成本可加;bug-report 上传涉及遥测边界,➖) | 小/➖ |
| `core/settings-diagnostics` | 设置诊断独立模块 | 部分:我们的 SettingsManager 有 diagnostics 列表,无独立模块 | 小 |

### 1.2 行为级新增(来自 CHANGELOG 0.85→1.1.0,✅ 已核实条目)

| 变更 | pi-python 现状 | 差距 |
|---|---|---|
| `agent_settled` 事件与 JSON 事件增加 `aborted` 字段(区分取消/完成) | 我们的 AgentSettled/事件无此字段 | **小,建议补**(事件契约级) |
| 工具事件增加 `durationMs`(真实执行时长,重载会话后仍在) | ToolExecutionEnd 有 usage 无 duration | **小,建议补** |
| `--tools +name/-name`(增删默认集而非替换)、`--tools` 支持 `*` 通配 | 我们的 `--tools` 是替换式 allowlist | 小-中 |
| 上下文估算 4 chars/token → 3.5(减少 context-limit 失败) | compaction 切点估算用 chars/4 | 小(一处常量+测试) |
| `server_busy`/Mistral error finish 重试修正 | DeepSeek-only;我们的 P8-T02 重试策略覆盖 5xx/429 | ➖ 核对 DeepSeek busy 语义即可 |
| OSC 7501 终端状态上报(working/blocked/done/failed) | 无 | 小,易加(TUI) |
| 会话成本按 prompt-length 阶梯计价修正 | usage/cost 已实现,DeepSeek 阶梯未见差异 | ➖ |
| Windows:剪贴板 Termux、Hyper-V 端口回退、`--watch` 图片 worker | 平台相关 | ➖ 视用户环境 |
| Claude Haiku 5.5 / GPT-6 Luna / llama.cpp 分类器 | 多 Provider divergence | ➖ |

### 1.3 上游未变的大面(与我们差距不变的)

interactive/json-event/print/rpc 四模式、七工具、session-manager、compaction、extensions loader、package-manager、slash-commands、skills、trust-manager、system-prompt、telemetry、event-bus、auth-storage、exec/bash-executor、tools/*(含 powershell)——这些我们的对应实现与差距已在 surface matrix 与既往验收中覆盖,不因 1.1.0 变化。

## 2. Oh My Pi(omp)模块清单与对照

omp = pi 的超集分发版(同源),在 pi 之上新增/重构 80+ 模块。按类别(行数为 src 实测):

### 2.1 工具集(`src/tools/`,73,355 行,~100 文件)——对比我们 7 工具

| omp 工具组 | 代表文件 | pi-python |
|---|---|---|
| 内建七工具增强 | bash-interactive/pty-selection/worktree-rewrite、bash-interceptor、write-content、read-format/read-binary/read-json/read-sqlite/read-pdf、ast-edit | 部分:bash/读文件有;格式化读/AST 编辑 ❌ |
| GitHub 套件 | gh / gh-pr-checkout / gh-pr-diff / gh-run-watch / gh-search / gh-view / gh-cache-invalidation | ❌ |
| 浏览器/桌面 | browser/、puppeteer/、computer(.)、image-gen、tts、stt | ❌ |
| 记忆 | memory-retain/recall/reflect/edit、learn | ❌(Phase 19 之外的独立能力) |
| 工作流 | plan-mode-guard、todo、wait、yield、think、report-tool-issue | 部分:todo/思考类可用 prompt 替代 |
| 安全 | security-scan、approval、auto-generated-guard | 部分:permission-gate 内建扩展(P10-T10) |
| 代码执行 | run-code、run-scope、eval、jtd-to-json-schema/typescript | ❌(与 codemode 同族) |
| 检索 | glob/grep(增强)、ast-grep、jfind、fetch | ✅ glob/grep 有;fetch/ast-grep ❌ |

### 2.2 会话层(`src/session/`,65,751 行,101 文件)

在 pi session-manager 之上新增:acp-permission-gate、anthropic/codex auto-reset、artifacts、async-job-delivery、auth-broker、bash-runner、blob-store、btw-turn(旁路提问)、cache-warmer、checkpoint-entries、claude/codex-session-store(读竞品会话)、client-bridge、code-mode、compact-modes、context-notes、file-recorder、fs-cache-invalidation、nested tool calls、output-meta、supersede/read-summary、speculation 执行、turn-budget、usage-totals 等。
pi-python:核心 session(-manager/runtime/events/recovery/repair/export)+ auto-compaction + branch summary ✅;上表多为 ❌,其中 checkpoint-entries(会话内检查点)与 usage-totals(累计用量)是低成本可补项。

### 2.3 模式层(`src/modes/`,51,267 行)

在 interactive/print/rpc/json 之外新增:**acp**(Zed Agent Client Protocol)、agent-hub(多代理 hub UI)、progress-hud、status-line-host、startup-composer、turn-budget、warp-events(Warp 终端)、oauth-manual-input、magic-keywords、loop-condition/loop-limit。
pi-python:interactive/print/json/rpc ✅;acp/agent-hub/hud ❌。

### 2.4 独立子系统(其余 60+ 模块)

| 类别 | 模块(行数) | 说明 |
|---|---|---|
| 记忆 | memories、mnemopi(3.3k)、memory-backend、hindsight(3.2k) | 三后端:off/local/hindsight 服务器;retain/recall/reflect 工具 |
| 上下文压缩 | compress(snapcompact,视觉位图压缩) | 对 vision 模型做帧压缩 |
| MCP | mcp(10,866 行) | 内建(见 §1.1) |
| 代码智能 | lsp(9,847)、dap(3,973)、ida(9 文件,反编译) | LSP 诊断/定义;调试适配 |
| 任务/子代理 | task(14,835):内置 agent 定义、workflow 命令、in-process 执行、完成度自评估;collab(5,017) | 对应我们 Phase 19,omp 已是成熟实现 |
| Web | web(27,934):firecrawl/kagi/parallel/x/search/scrapers | 搜索/抓取套件 |
| 扩展性 | extensibility(23,687) | 扩展运行时增强 |
| 工作流/AI | goals、plan-mode(审批/移交/保护/自动存盘完整状态机)、autolearn/autoresearch/auto-thinking、speculation(1 文件,推测执行)、ratchet、judgment、if-bench、advisor(12 文件) | 高阶自治工作流 |
| 语音 | stt、tts | 语音输入/输出 |
| 安全 | security(4,887)、secrets(4,381)、cleanse(3,449) | 扫描/密钥/清洗 |
| 可观测 | stats、omp-stats(npm 包,本地仪表盘)、telemetry-export(+otlp)、eval(14,642)、if-bench | 用量统计/评测基准 |
| 集成 | ssh、irc、cursor(.ts)、cursor-bridge-tools、exa(3 文件)、markit(8)、markitdown 类 | 各类桥接 |
| 基础设施 | blob-broker(9,060)、internal-urls(8,424)、discovery(9,662)、launch、subprocess(3,123)、tiny(13 文件)、archive、downloads、debug | 内容寻址存储/内部 URL/发现 |

## 3. pi-python 模块对照总表

| pi-python 模块 | Pi 1.1.0 对应 | omp 对应 | 状态 |
|---|---|---|---|
| pi_telemetry | core/telemetry | telemetry-export(+otlp) | ✅ 协议对等(no-op/memory);导出 ❌ |
| pi_ai(messages/events/stream/provider/wire) | packages/ai | @oh-my-pi/pi-ai(自动模型发现) | ✅ 核心对等;模型目录宽度 ➖;自动发现 ❌ |
| pi_agent(loop/queues/cancellation/listeners/scheduler) | packages/agent | @oh-my-pi/pi-agent-core(transport 抽象、attachments) | ✅ 核心对等;transport 抽象/attachments ❌ |
| pi_tui | packages/tui | @oh-my-pi/pi-tui(差分渲染) | ✅ 基础对等;差分渲染/高级组件 🟡 |
| cli/parser+surface+main | cli/args、main | src/cli(27.9k) | ✅ 静态面完整;omp 规模大一个量级 |
| cli/run+file_args | modes/print-mode、cli/file-processor | modes/print-mode | ✅ |
| tui/runner+main+renderers | modes/interactive | modes/interactive-mode+components+controllers | ✅ 核心对等;omp 更丰富(hub/hud) ❌ |
| rpc/(server/client/commands/framing) | modes/rpc、rpc-entry | modes/rpc | ✅ |
| sdk.py | core/sdk | sdk.ts | ✅ |
| session/*(manager/reader/tree/recovery/repair/export/fork) | core/session-manager、session-export | src/session(65.7k) | ✅ 核心对等;omp 会话增强清单大面积 ❌ |
| compaction/* | core/compaction | compress + compact-modes | ✅ 文本压缩对等;snapcompact 视觉压缩 ❌ |
| tools/*(七工具) | core/tools | src/tools(73.4k,~100 文件) | ✅ 七工具对等;其余 ~90 文件 ❌ |
| resources/*(settings/trust/discovery/skills/prompts/themes) | core/settings-manager、resource-loader、skills、trust-manager | src/config(16.6k)+discovery | ✅ |
| extensions/*(loader/runtime/registry/hooks/api) | core/extensions(loader/runner/types/wrapper) | src/extensibility(23.7k) | ✅ Python 侧对等;omp 规模大 |
| packages/*(spec/resolver/manifest/manager/npm_data) | package-manager-cli、core/package-manager | discovery | ✅ |
| export/html.py | core/session-export(1.1.0 新) | — | ✅(P17-T03) |
| node_host/* + node/extension-host | (上游无此概念——宿主即 TS) | — | ✅ 架构等价物(我们反过来用 Node host 跑 TS 扩展) |
| — | core/mcp-servers + extensions/mcp | src/mcp(10.9k) | ✅ Phase 18(stdio transport/Host 生命周期/映射/deferred 激活/Package 声明/产品 E2E;OAuth 生命周期 ❌ Post-v1) |
| — | extensions/codemode + core/nested-tool-calls | src/tools/run-code、session/code-mode | ❌ 已评估(P18.5-T03,见 §4 C 级) |
| — | extensions/tool-search | — | ✅ P18-T04 deferred 工具(mcp_search + 增量激活) |
| — | core/cache-warmer、settings-diagnostics | — | ❌/🟡 候选 |
| — | core/virtual-models | — | ✅ P18.5-T02(settings virtualModels 别名 → 真实模型 + thinking 覆盖) |
| — | — | usage-totals/checkpoint-entries | 🟡 usage-totals ✅ P18.5-T01(纯聚合);checkpoint-entries 候选 |
| — | — | memories/mnemopi/hindsight、task、lsp/dap、web、acp、voice、security、eval、gh-* | ❌(Phase 19+ / 不排期) |

## 4. 差距分级与建议

### A 级(✅ 已全部闭环,2026-10-10,分支 phase/18-gap-closure)
1. ✅ `agent_settled` 补 `aborted` 字段(abort 后中端流验证 aborted=True);
2. ✅ 工具事件补 `durationMs`(tool_execution_end 扩展事件 + ToolResultMessage.details
   持久化,重载会话后仍在);
3. ✅ compaction 估算 4 → 3.5 chars/token(常量测试锁定);
4. ✅ `--tools +name/-name` 增量语法与 `*`/`?`/`[...]` 通配(增量基准为默认四工具;
   `mcp__*` 模式穿透至扩展层);
5. ✅ crash-log:顶层异常落盘 `agent/crash/<stamp>-<pid>/`(error.txt + meta.json +
   最近 100 条 entries;best-effort,失败不遮蔽原异常);CLI main 已接线。

### B 级(✅ MCP 已全部闭环,2026-10-25,分支 phase/18-mcp;子代理见 Phase 19 排期)
- ✅ MCP(P18-T01~T06):stdio JSON-RPC transport(握手/超时/结构化错误)、McpHost 生命周期
  (看门狗/崩溃重启上限/按代关闭)、Tool/Prompt/content 双向映射(JSON schema→pydantic、
  isError→异常)、deferred 工具激活(`mcp_search` 紧凑工具 + 工具执行后增量注入)、
  Package 声明(`package.json#pi.mcpServers` + install/restart/remove 与 Host 状态一致)、
  产品 E2E(调用/断线恢复/abort/switch/干净退出,`tests/fixtures/mcp_server`)。
  与上游 1.1.0 的差异:OAuth 生命周期(超时/取消/端口回退)与 `/mcp` 实时管理面板未做
  (Post-v1);工具命名沿用真实工具名 + `server` 元数据,未引入 `mcp__server__tool`
  前缀(会话内以 server 归属区分,避免与用户工具名冲突语义)。

### C 级(快速项已闭环,2026-10-25,P18.5;其余候选维持)
- ✅ **usage-totals**(P18.5-T01):`session/usage_totals.py` 纯聚合(requests/input/output/
  cache/tokens/cost),assistant 消息累计,畸形值按 0(untrusted settings 原则)。
- ✅ **virtual-models**(P18.5-T02):settings `virtualModels`(config 边界校验)→
  `--model 别名` 在 CLI/RPC/TUI 三入口解析到真实模型 + thinking 覆盖;真实模型名优先,
  避免遮蔽。
- **codemode + nested-tool-calls 评估结论**(P18.5-T03,不实现,留给独立阶段):
  - nested-tool-calls 是 codemode 的前置:需要 pi_agent 工具管线支持重入执行
    (`execute` 内发起子工具调用)、`parentToolCallId` 关联、usage 归账到外层调用、
    abort 信号沿嵌套链传播。这触及执行循环核心(事件语义/取消/归账),属跨包
    (pi_agent + pi_coding_agent)改造,估算为一个独立 Phase(3~4 个任务:契约、
    重入执行、预算与取消、产品接线)。
  - codemode 的 Python 侧形态建议复用既有 Node host:JS 代码在 host 内执行,
    经 `execute_tool` 回调 Python 管线(等价上游 `pi.tools.*`),避免自建 JS 运行时;
    沙箱边界(上游 isolated-vm 语义)在 dist 层面未逐行核实,实施前需先固化
    允许的宿主能力面与超时/输出上限。
  - 建议:作为 P21 后的独立阶段(P20/P21 完成后),先 nested 后 codemode。
- 其余候选维持:checkpoint-entries、cache-warmer、LSP/DAP、记忆后端(local)、
  web 工具包、AOC 7501。

### ➖ 有意 divergence(维持)
- 多 Provider 目录与分类器模型(单 DeepSeek 是项目架构决策);
- bug-report 上传、telemetry 上报(遥测边界);
- omp 的语音/acp/irc/cursor 等集成(超出重写范围)。

### 风险与说明
- 本分析的 Pi 侧基于 1.1.0 dist(编译产物)与 CHANGELOG;行为细节(如 codemode 沙箱边界)未逐行核实,标注为推断。
- omp 是快速演进的大规模 fork,本文行数/清单为 18.10.1 快照。
- 我们的语义差分 oracle 仍锚定 0.84.1;若决定跟进 1.1.0 的行为变更(如 3.5 chars/token),应先更新 oracle 基线再改实现,避免静默漂移。
