# Python Pi Agent 重写任务清单

> 总体方案见 `tasks/plan.md`。  
> 每项任务目标规模为 1–5 个文件；若实现前发现超过 5 个文件，必须先拆分。  
> 默认验证命令不运行真实 API；`live_provider` 必须显式触发。

## Phase 0：规范与测试底座

### P0-T01：冻结源码行为基线

- [ ] **描述：** 记录 `D:\pi` commit、稳定 CLI 主链、未完成 Harness 边界和教程版本。
- [ ] **验收：** `docs/baseline.md` 能让新开发者区分事实、教程解释和推断。
- [ ] **验证：** 路径和符号通过 `rg` 在固定 commit 中可找到。
- [ ] **依赖/规模：** 无；S；`docs/baseline.md`、`docs/parity-matrix.md`。

### P0-T02：建立 uv workspace

- [ ] **描述：** 创建 root `pyproject.toml` 和核心 package 空壳，固定单向 import 关系。
- [ ] **验收：** 所有 package 可 editable install，空包可导入。
- [ ] **验证：** `uv sync --all-packages`；最小 import smoke test。
- [ ] **依赖/规模：** P0-T01；M；root 配置和每次最多 3 个 package manifest，分批提交。

### P0-T03：建立隔离测试环境

- [ ] **描述：** 配置 pytest markers、isolated HOME、清空 API Key、禁止网络、固定 clock/UUID。
- [ ] **验收：** 默认测试访问网络或真实用户配置时立即失败。
- [ ] **验证：** `uv run pytest tests/test_test_environment.py`。
- [ ] **依赖/规模：** P0-T02；M；`conftest.py`、测试配置和一份自测。

### P0-T04：建立质量门禁

- [ ] **描述：** 配置 ruff、mypy、coverage 和 package import-boundary check。
- [ ] **验收：** 人为加入反向 import 时测试失败，删除后通过。
- [ ] **验证：** ruff、mypy、focused dependency test。
- [ ] **依赖/规模：** P0-T02；S；root 配置与一份架构测试。

### P0-T05：编写五份公共契约

- [ ] **描述：** 明确 Message、stream events、Agent events、Tool pipeline、Session JSONL。
- [ ] **验收：** 每份文档有输入、输出、顺序、不变量和错误语义。
- [ ] **验证：** 人工对照 `D:\pi` 源码和测试审查。
- [ ] **依赖/规模：** P0-T01；每份 XS，逐份完成。

## Phase 1：FakeProvider 可行走骨架

### P1-T01：定义最小消息模型

- [ ] **描述：** 实现 User/Assistant/ToolResult、Text/ToolCall、Usage 和 StopReason。
- [ ] **验收：** 判别联合可验证、序列化、反序列化并保持 tool call id。
- [ ] **验证：** round-trip 与非法 payload 表驱动测试。
- [ ] **依赖/规模：** P0-T05；M；`pi_ai/messages.py`、`content.py`、测试。

### P1-T02：实现 AssistantStream

- [ ] **描述：** 实现 async iteration、partial message reducer、`result()` 和单终止约束。
- [ ] **验收：** text/tool-call/error 流只产生一个 terminal event。
- [ ] **验证：** golden event tests，含重复终止和取消。
- [ ] **依赖/规模：** P1-T01；M；stream 模块、event 模型、测试。

### P1-T03：实现共享 FakeProvider

- [ ] **描述：** 提供可排队响应、delta、tool call、error、abort 的确定性 Provider。
- [ ] **验收：** 所有上层测试可只注入 FakeProvider，不 mock 私有方法。
- [ ] **验证：** 精确事件序列和响应队列耗尽测试。
- [ ] **依赖/规模：** P1-T02；S；testing provider 与测试。

### P1-T04：实现最小串行 Agent Loop

- [ ] **描述：** 完成 model -> tool -> result -> model 的串行闭环。
- [ ] **验收：** 直接回答、单工具、多轮工具三条路径均结束于 final assistant。
- [ ] **验证：** 三份 golden transcript。
- [ ] **依赖/规模：** P1-T01–T03；M；loop、tool protocol、测试。

### P1-T05：实现 Fake print CLI

- [ ] **描述：** 创建内存 CodingSession 和 `python -m pi_coding_agent -p`。
- [ ] **验收：** 输入 prompt 后只输出 FakeProvider 最终文本。
- [ ] **验证：** 黑盒 subprocess test。
- [ ] **依赖/规模：** P1-T04；M；session、cli、`__main__`、测试。

## Phase 2：pi_ai 与 DeepSeek

### P2-T01：补齐 AI 层数据契约

- [ ] **描述：** 增加 Thinking/Image content、Model、Context、ToolSpec、ThinkingLevel、完整 Usage。
- [ ] **验收：** 所有类型 round-trip，未知 discriminator 明确失败。
- [ ] **验证：** schema 与 serialization contract tests。
- [ ] **依赖/规模：** Phase 1；分成 2 个 M task，单次不超过 5 文件。

### P2-T02：实现 Registry 与 CredentialResolver

- [ ] **描述：** 实现 Provider/Model 注册、查找、覆盖以及环境变量凭据解析。
- [ ] **验收：** 可枚举认证状态但任何 repr/diagnostic 不含 secret。
- [ ] **验证：** 注册冲突、缺凭据、脱敏和环境隔离测试。
- [ ] **依赖/规模：** P2-T01；M；registry、credentials、测试。

### P2-T03：实现 OpenAI-compatible 编码器

- [ ] **描述：** 把内部 Context/Tool 转成 chat completions 请求，并解析非流式响应。
- [ ] **验收：** user/assistant/tool result、thinking 配置和多个 tools 转换正确。
- [ ] **验证：** MockTransport request-body contract tests。
- [ ] **依赖/规模：** P2-T01；M；codec、adapter、测试。

### P2-T04：实现 SSE 流解析

- [ ] **描述：** 解析 text/thinking/tool-call delta，累积部分 JSON 参数并规范化 stop reason。
- [ ] **验收：** 断片边界任意切分仍得到同一事件序列。
- [ ] **验证：** chunk fuzz/table tests，含非法 SSE 和中途断流。
- [ ] **依赖/规模：** P2-T03；M；SSE parser、stream adapter、测试。

### P2-T05：注册并验证 DeepSeek

- [ ] **描述：** 注册 base URL、模型元数据、`DEEPSEEK_API_KEY` 和 thinking 映射。
- [ ] **验收：** mock 测试通过；显式 live test 可完成文本、流和 tool call。
- [ ] **验证：** `pytest -m live_provider --provider deepseek --model deepseek-v4-flash`。
- [ ] **依赖/规模：** P2-T02–T04；S；provider config、live test。

## Phase 3：完整 Agent Core

### P3-T01：实现 AgentEvent 与 AgentState reducer

- [ ] **描述：** 增加 Agent/Turn/Message/Tool 生命周期事件和状态归约。
- [ ] **验收：** 监听器看到的是事件对应的已更新状态。
- [ ] **验证：** 严格事件顺序与状态快照测试。
- [ ] **依赖/规模：** Phase 1；M；events、state/reducer、测试。

### P3-T02：实现 awaited listener barrier

- [ ] **描述：** 支持 sync/async listener，按注册顺序等待并正确处理取消。
- [ ] **验收：** prompt 返回前 listener 全部完成；核心 listener 异常可见。
- [ ] **验证：** delayed listener、exception、wait-for-idle tests。
- [ ] **依赖/规模：** P3-T01；S；event bus 与测试。

### P3-T03：实现工具五步管道

- [ ] **描述：** prepare -> validate -> before -> execute -> after -> ToolResult。
- [ ] **验收：** unknown tool、invalid args、blocked、exception 都形成结构化结果。
- [ ] **验证：** 表驱动 pipeline tests。
- [ ] **依赖/规模：** P1-T04、P3-T01；M；tool executor、hooks、测试。

### P3-T04：实现并行批次语义

- [ ] **描述：** 支持 sequential/parallel；准备串行、execute 并行、结果稳定排序。
- [ ] **验收：** end event 按完成顺序，transcript 按源调用顺序。
- [ ] **验证：** 使用受控 event 的并发测试重复三次。
- [ ] **依赖/规模：** P3-T03；M；batch executor 与测试。

### P3-T05：实现取消与终止

- [ ] **描述：** 支持 abort、late update guard、length 截断、terminate 和最大轮数。
- [ ] **验收：** 截断 tool call 不执行；取消后无新消息污染下一次运行。
- [ ] **验证：** abort-before/during/after、late callback tests。
- [ ] **依赖/规模：** P3-T02–T04；M；cancellation、loop adjustments、测试。

### P3-T06：实现 steering 与 follow-up

- [ ] **描述：** 创建两个语义不同的队列以及 prepare-next-turn/stop-after-turn。
- [ ] **验收：** steering 在工具批次后注入，follow-up 在原任务结束后开始。
- [ ] **验证：** 多队列顺序和 continue tests。
- [ ] **依赖/规模：** P3-T05；M；queue、agent facade、测试。

## Phase 4：Coding Tools

### P4-T01：定义 Operations 边界

- [ ] **描述：** 定义 File/Process/Search Operations Protocol 和本地实现入口。
- [ ] **验收：** Tool 不直接调用散落的 os/subprocess API。
- [ ] **验证：** fake operations contract tests。
- [ ] **依赖/规模：** Phase 3；S；operations contract、fake、测试。

### P4-T02：实现 read 与输出截断

- [ ] **描述：** 支持 offset/limit、文本/图片/二进制检测、UTF-8 安全 head 截断。
- [ ] **验收：** 截断结果报告原规模和完整输出位置。
- [ ] **验证：** 中文、emoji、超大行、越界和二进制 tests。
- [ ] **依赖/规模：** P4-T01；M；read、truncate、测试。

### P4-T03：实现 write 与 edit

- [ ] **描述：** write 创建父目录；edit 原子匹配，保存 BOM/CRLF。
- [ ] **验收：** 重叠/缺失/重复目标整体失败且文件未改变。
- [ ] **验证：** temp filesystem 与 byte-for-byte tests。
- [ ] **依赖/规模：** P4-T01；拆为两个 M task，各自不超过 4 文件。

### P4-T04：实现文件 mutation queue

- [ ] **描述：** 同一规范路径串行，不同路径可并行，符号链接别名归一。
- [ ] **验收：** 并发 edit/write 不丢更新。
- [ ] **验证：** controlled concurrency 与 symlink tests。
- [ ] **依赖/规模：** P4-T03；S；queue 与测试。

### P4-T05：实现 bash

- [ ] **描述：** 支持 cwd/env/timeout/abort、stdout/stderr 合并、tail 截断和进程树清理。
- [ ] **验收：** timeout/abort 后无孤儿进程，迟到输出被丢弃。
- [ ] **验证：** Windows PowerShell/cmd 与 Linux shell matrix。
- [ ] **依赖/规模：** P4-T01–T02；M；process operations、bash tool、测试。

### P4-T06：实现 grep/find/ls

- [ ] **描述：** 支持 `.gitignore`、隐藏文件、结果上限、flag-like pattern。
- [ ] **验收：** 三个工具返回稳定相对路径和明确截断说明。
- [ ] **验证：** 临时 Git tree contract tests。
- [ ] **依赖/规模：** P4-T01；拆成 3 个 S task。

## Phase 5：CodingSession 与 Headless CLI

### P5-T01：实现 CodingSession composition root

- [ ] **描述：** 组合 ModelRuntime、Agent、Tools、Settings stub 和内存 Session。
- [ ] **验收：** 下层依赖均通过构造注入，核心不读全局单例。
- [ ] **验证：** FakeProvider integration test。
- [ ] **依赖/规模：** Phase 2–4；M；services、session、factory、测试。

### P5-T02：实现 CLI 参数契约

- [ ] **描述：** 支持 help/version/list-models/provider/model/thinking/tools/no-session/print。
- [ ] **验收：** 错误参数有稳定退出码和 stderr 诊断。
- [ ] **验证：** 参数表驱动测试和黑盒 subprocess tests。
- [ ] **依赖/规模：** P5-T01；M；args、main、测试。

### P5-T03：实现 text 与 JSON 输出

- [ ] **描述：** text 只打印最终文本，JSON 每行一个事件，不混入日志。
- [ ] **验收：** assistant error 返回非零；stderr 不含 secret。
- [ ] **验证：** stdout cleanliness 和 JSON parse tests。
- [ ] **依赖/规模：** P5-T02；S；print/json mode、测试。

### P5-T04：完成真实 DeepSeek 工具闭环

- [ ] **描述：** 在临时 workspace 运行真实 prompt -> read -> ToolResult -> final answer。
- [ ] **验收：** 结构化断言证明文件确实被读取，限制 token 和费用。
- [ ] **验证：** 显式 live_provider smoke test。
- [ ] **依赖/规模：** P2-T05、P4-T02、P5-T03；S；live test 与文档。

## Phase 6：Session Tree

### P6-T01：定义 Session Header 与 Entry 联合

- [ ] **描述：** 定义 versioned header 和全部成熟路径 entry 类型。
- [ ] **验收：** round-trip 保留 message、usage、thinking、stop reason 和 parent id。
- [ ] **验证：** schema/codec contract tests。
- [ ] **依赖/规模：** Phase 5；M；entries、codec、测试。

### P6-T02：实现 InMemory Repository

- [ ] **描述：** 实现 append/load/leaf/path/fork 的参考后端。
- [ ] **验收：** 重复 ID、未知 parent 和非法 sequence 被拒绝。
- [ ] **验证：** shared repository conformance suite。
- [ ] **依赖/规模：** P6-T01；M；protocol、memory repo、conformance。

### P6-T03：实现 JSONL Repository

- [ ] **描述：** 每次 mutation append 一行，支持加载和连续 sequence。
- [ ] **验收：** 与 InMemory 运行同一套 conformance tests。
- [ ] **验证：** crash/reopen 和跨进程 smoke test。
- [ ] **依赖/规模：** P6-T02；M；jsonl repo、codec adjustments、测试。

### P6-T04：实现损坏恢复边界

- [ ] **描述：** 修复无换行/torn tail；拒绝中间损坏和完整非法行。
- [ ] **验收：** 不会静默丢弃有效历史。
- [ ] **验证：** byte fixture corruption matrix。
- [ ] **依赖/规模：** P6-T03；S；recovery helper 与测试。

### P6-T05：实现 Context 重建与分支

- [ ] **描述：** 从 leaf 回溯、反转，应用 model/thinking/compaction，支持 branch/fork/tree。
- [ ] **验收：** 非活动分支不进入 Context；状态随分支回退。
- [ ] **验证：** tree fixtures 和 context golden tests。
- [ ] **依赖/规模：** P6-T02–T04；分成 context 与 branch 两个 M task。

### P6-T06：建立副作用恢复幂等性

- [ ] **描述：** 根据已持久化 ToolCall/ToolResult 判定恢复点。
- [ ] **验收：** resume 不重新执行已完成 write/edit/bash。
- [ ] **验证：** crash-between-events matrix。
- [ ] **依赖/规模：** P6-T05、Phase 4；M；resume policy、session integration test。

## Phase 7：Resources 与 Trust

### P7-T01：实现 Settings 合并

- [ ] **描述：** 解析 global/project settings，明确覆盖和未知字段诊断。
- [ ] **验收：** 未信任项目配置不启用可执行资源。
- [ ] **验证：** temporary HOME/project matrix。
- [ ] **依赖/规模：** Phase 5；M；settings model、manager、测试。

### P7-T02：实现 System Prompt 与 Context Files

- [ ] **描述：** 组装 cwd/date/tools，按层级读取 AGENTS.md/CLAUDE.md。
- [ ] **验收：** 合并顺序、XML escaping 和缺文件行为确定。
- [ ] **验证：** nested directory golden tests。
- [ ] **依赖/规模：** P7-T01；M；prompt builder、context loader、测试。

### P7-T03：实现 Prompt Templates

- [ ] **描述：** 发现 Markdown template 并展开位置参数、全部参数和默认值。
- [ ] **验收：** 错误模板产生 diagnostic，不破坏普通 prompt。
- [ ] **验证：** parser/expansion tests。
- [ ] **依赖/规模：** P7-T02；S；template module、测试。

### P7-T04：实现 Skills

- [ ] **描述：** frontmatter、scope、优先级、冲突、索引、懒加载、显式 `/skill`。
- [ ] **验收：** 正文默认不进 system prompt；禁用模型调用的 skill 不出现在索引。
- [ ] **验证：** collision/frontmatter/XML tests。
- [ ] **依赖/规模：** P7-T02；拆 discovery 与 expansion 两个 M task。

### P7-T05：实现 ResourceLoader 与 ProjectTrust

- [ ] **描述：** 聚合 settings/context/skills/templates/diagnostics，支持 reload。
- [ ] **验收：** 不可信项目的 executable extension 不加载。
- [ ] **验证：** trust/reload/stale resource tests。
- [ ] **依赖/规模：** P7-T01–T04；M；loader、trust manager、测试。

## Phase 8：可靠性与上下文压缩

### P8-T01：实现 Provider Retry

- [ ] **描述：** 分类 transient/permanent 错误，支持可取消 backoff。
- [ ] **验收：** 429/账单错误不被错误重试，网络断流可恢复。
- [ ] **验证：** fake clock retry tests。
- [ ] **依赖/规模：** Phase 2、5；M；retry policy、session integration、测试。

### P8-T02：实现 Context Usage 与阈值

- [ ] **描述：** 计算最后有效 usage、估算 fallback、reserve/keep recent 阈值。
- [ ] **验收：** 纯逻辑对中英文偏差有明确记录和安全余量。
- [ ] **验证：** table tests。
- [ ] **依赖/规模：** Phase 6；S；usage module、测试。

### P8-T03：实现 Compaction 切点

- [ ] **描述：** 合法切点、recent tail、assistant split、turn prefix 和文件跟踪。
- [ ] **验收：** 不从 ToolResult 非法切断；结果确定性。
- [ ] **验证：** large fixture 与 property tests。
- [ ] **依赖/规模：** P8-T02；M；cutpoint、serialization、测试。

### P8-T04：实现摘要生成与存储

- [ ] **描述：** 使用 FakeSummarizer 测试结构化摘要、previous summary 和 CompactionEntry。
- [ ] **验收：** 下一次 Context 为 summary + retained tail。
- [ ] **验证：** multi-compaction integration tests。
- [ ] **依赖/规模：** P8-T03、Phase 6；M；summarizer、compaction service、测试。

### P8-T05：实现自动压缩与 overflow 恢复

- [ ] **描述：** 支持 manual/threshold/overflow，overflow 自动恢复最多一次。
- [ ] **验收：** 不出现无限 compact/retry 循环。
- [ ] **验证：** fake provider overflow sequences。
- [ ] **依赖/规模：** P8-T01、T04；M；session orchestration、测试。

### P8-T06：实现 Branch Summary 与 agent_settled

- [ ] **描述：** 用 LCA 收集放弃分支，生成摘要；所有后处理完成后发 settled。
- [ ] **验收：** branch summary 不污染原分支，settled 晚于 retry/compact/listener。
- [ ] **验证：** branch tree 和 event ordering tests。
- [ ] **依赖/规模：** P8-T04–T05；M；branch summary、settlement、测试。

## Phase 9：Extensions 与 Packages

### P9-T01：定义 Extension API 契约

- [ ] **描述：** 定义 input/context/provider/tool/session hook 的 typed 输入输出和错误策略。
- [ ] **验收：** 每个 hook 写明继续、阻止、改写或终止语义。
- [ ] **验证：** contract review 与 schema tests。
- [ ] **依赖/规模：** Phase 7–8；M；types、contracts、测试。

### P9-T02：实现后台 Hook Pipeline

- [ ] **描述：** 按源码顺序调度 hook，隔离第三方错误并传播取消。
- [ ] **验收：** command/input/skill/preflight/before-agent/tool 顺序固定。
- [ ] **验证：** golden hook trace。
- [ ] **依赖/规模：** P9-T01；M；runner、session integration、测试。

### P9-T03：实现扩展注册能力

- [ ] **描述：** 注册 Tool、Command、Provider、Flag 和 custom Session entry。
- [ ] **验收：** Extension command 不消耗模型响应；动态 tool 进入 system prompt。
- [ ] **验证：** registration integration tests。
- [ ] **依赖/规模：** P9-T02；按注册类型拆为多个 S task。

### P9-T04：实现 Extension Loader 与 Trust

- [ ] **描述：** 支持 user/project/local module/entry point，含 reload、shutdown、stale context。
- [ ] **验收：** 未信任 project extension 不执行；reload 后旧 context 失效。
- [ ] **验证：** isolated module tests。
- [ ] **依赖/规模：** P9-T02、P7-T05；M；loader、runtime、测试。

### P9-T05：实现 Package Manifest 最小闭环

- [ ] **描述：** 解析资源 manifest，支持安装记录、启用/禁用和诊断。
- [ ] **验收：** 包资源仍经过 scope/trust/priority 规则。
- [ ] **验证：** temporary package repository tests。
- [ ] **依赖/规模：** P9-T03–T04；M；manifest、package state、测试。

## Phase 10：TUI

### P10-T01：定义 Terminal 与 VirtualTerminal

- [ ] **描述：** 抽象 write/move/clear/size/mode，提供内存终端。
- [ ] **验收：** 不启动真实控制台也能验证 viewport。
- [ ] **验证：** terminal conformance tests。
- [ ] **依赖/规模：** P0-T02；M；terminal protocol、virtual terminal、测试。

### P10-T02：实现宽度与差分渲染

- [ ] **描述：** 处理 ANSI、wcwidth、CJK/emoji、wrap、shrink、resize。
- [ ] **验收：** 80x24/40x10/resized viewport 无残影。
- [ ] **验证：** screen golden tests。
- [ ] **依赖/规模：** P10-T01；分 width/layout/renderer 三个 M task。

### P10-T03：实现编辑器与输入解析

- [ ] **描述：** editor/history/undo/paste/escape/CSI/Kitty 输入和 word navigation。
- [ ] **验收：** 分段输入与 bracketed paste 不丢字符。
- [ ] **验证：** byte-stream parser 和 editor model tests。
- [ ] **依赖/规模：** P10-T01；拆 parser 与 editor 两个 M task。

### P10-T04：实现 Agent 消息渲染

- [ ] **描述：** 渲染 text/thinking/tool progress/error/usage/context/cost。
- [ ] **验收：** 只消费 Event/State 公共 API，不维护第二份 transcript。
- [ ] **验证：** FakeProvider streaming screen tests。
- [ ] **依赖/规模：** P10-T02、Phase 5；M；renderers、controller、测试。

### P10-T05：实现交互命令与 Overlay

- [ ] **描述：** model/settings/session/tree/compact selectors 和核心 slash commands。
- [ ] **验收：** overlay focus、取消、session switch 行为确定。
- [ ] **验证：** VirtualTerminal interactive tests。
- [ ] **依赖/规模：** P10-T03–T04、Phase 6–9；按 overlay 拆多个 M task。

### P10-T06：完成 Windows ConPTY Smoke

- [ ] **描述：** 在真实 Windows Terminal/ConPTY 验证启动、流式、resize、中止和退出。
- [ ] **验收：** 无残留 raw mode，无孤儿进程。
- [ ] **验证：** 标记为 `tui_live` 的平台 smoke test。
- [ ] **依赖/规模：** P10-T05；S；smoke harness 与文档。

## Phase 11：Provider 广度与认证

### P11-T01：建立 Adapter Contract Suite

- [ ] **描述：** 固化 message/tool/thinking/cache/usage/error/abort 的协议族契约。
- [ ] **验收：** 任意 adapter 可用同一套测试运行。
- [ ] **验证：** DeepSeek adapter 先通过完整 suite。
- [ ] **依赖/规模：** Phase 2；M；conformance helper 与 fixtures。

### P11-T02：实现主协议族

- [ ] **描述：** 分别实现 OpenAI Responses、Anthropic Messages、Google 和 Bedrock。
- [ ] **验收：** 每个 adapter 只依赖 `pi_ai`，不修改 Agent Loop。
- [ ] **验证：** 每个协议族独立 contract + mock HTTP tests。
- [ ] **依赖/规模：** P11-T01；每个协议族单独 L task并继续细拆。

### P11-T03：实现 Provider 配置层

- [ ] **描述：** 将多个具体 Provider 映射到协议 adapter 和模型元数据。
- [ ] **验收：** 新 Provider 主要是声明配置而不是复制网络实现。
- [ ] **验证：** registry/model lookup tests。
- [ ] **依赖/规模：** P11-T02；按 Provider family 分 S task。

### P11-T04：实现 OAuth 与 Credential Refresh

- [ ] **描述：** 建立可取消 OAuth flow、持久凭据和 refresh single-flight。
- [ ] **验收：** 并发请求不重复 refresh，任何状态输出都不含 token。
- [ ] **验证：** fake OAuth server 与 race tests。
- [ ] **依赖/规模：** P11-T03；拆 auth store/flow/refresh 三个 M task。

### P11-T05：实现动态模型目录

- [ ] **描述：** 支持远程刷新、cache、失败回退、配置覆盖和热重载。
- [ ] **验收：** 网络失败不阻塞使用已有目录，取消不挂起启动。
- [ ] **验证：** fake catalog server tests。
- [ ] **依赖/规模：** P11-T03；M；catalog、cache、测试。

## Phase 12：RPC 与远程包

### P12-T01：完成 JSON/RPC 模式

- [ ] **描述：** 实现 request id、commands、events、errors 和 stdin/stdout framing。
- [ ] **验收：** stdout 每行合法 JSON，未知 command 有稳定错误。
- [ ] **验证：** black-box RPC tests。
- [ ] **依赖/规模：** Phase 5–9；M；rpc protocol、mode、测试。

### P12-T02：实现 pi_protocol

- [ ] **描述：** Pydantic schema、CBOR、4-byte big-endian framing 和 16 MiB 上限。
- [ ] **验收：** partial frame、oversize、invalid CBOR 明确失败。
- [ ] **验证：** codec/framing contract tests。
- [ ] **依赖/规模：** P0-T02；M；schema、codec、framing、测试。

### P12-T03：实现 pi_client

- [ ] **描述：** 连接、request、event、session handle、lease、reconnect、dispose。
- [ ] **验收：** 断线恢复不重复提交已确认请求。
- [ ] **验证：** fake transport state-machine tests。
- [ ] **依赖/规模：** P12-T02；按 connection/session 拆两个 M task。

### P12-T04：实现 pi_server

- [ ] **描述：** connection、transport、多 Session 生命周期和请求分派。
- [ ] **验收：** 租约和断线规则明确，异常 Session 不拖垮 server。
- [ ] **验证：** client/server conformance tests。
- [ ] **依赖/规模：** P12-T02–T03、Phase 6；拆 transport/session 两个 M task。

### P12-T05：实现 SQLite Backend

- [ ] **描述：** 让 SQLite 与 InMemory/JSONL 运行同一 repository conformance。
- [ ] **验收：** 事务失败不发布半成品，sequence/parent 不变量一致。
- [ ] **验证：** backend conformance + crash tests。
- [ ] **依赖/规模：** Phase 6；M；sqlite repo、migration、测试。

### P12-T06：探索实验 AgentHarness

- [ ] **描述：** 按上游接口实现 operation records、lanes、resume 等实验语义。
- [ ] **验收：** 明确标记 experimental，不替换成熟 CodingSession。
- [ ] **验证：** 独立 harness contract tests，不与稳定 release gate 混淆。
- [ ] **依赖/规模：** P12-T05；先写 ADR，再拆为多个 M task。

## Phase 13：产品外围

### P13-T01：实现导入导出

- [ ] **描述：** HTML/JSONL export、JSONL import 和 round-trip。
- [ ] **验收：** 消息、entry、分支、usage 不丢失。
- [ ] **验证：** export/import golden tests。
- [ ] **依赖/规模：** Phase 6、10；按格式拆 S/M task。

### P13-T02：实现图片与剪贴板

- [ ] **描述：** 图片附件、mime/size 校验、剪贴板输入和终端图片后端。
- [ ] **验收：** 不支持的终端自动降级文本，不阻塞核心 TUI。
- [ ] **验证：** image fixture、clipboard fake、terminal capability tests。
- [ ] **依赖/规模：** Phase 2、10；拆附件与渲染两个 M task。

### P13-T03：完善 Package Manager

- [ ] **描述：** 来源解析、安装、升级、禁用、锁定和诊断。
- [ ] **验收：** 安装失败不破坏既有资源状态，project 资源经过 trust。
- [ ] **验证：** local fake registry/git tests。
- [ ] **依赖/规模：** P9-T05；按 source/state/update 拆三个 M task。

### P13-T04：完善平台集成

- [ ] **描述：** theme、keybindings、completion、first-run、自更新和安装器。
- [ ] **验收：** Windows/Linux 从全新 HOME 启动正常。
- [ ] **验证：** packaged install smoke matrix。
- [ ] **依赖/规模：** Phase 10、P13-T03；逐功能拆 S/M task。

## Phase 14：Telemetry、Evals 与发布

### P14-T01：实现 Telemetry Protocol

- [ ] **描述：** no-op、in-memory、real exporter 和测试采集器。
- [ ] **验收：** telemetry 故障不改变 Agent 语义，不记录 secret/tool 原始敏感内容。
- [ ] **验证：** telemetry conformance tests。
- [ ] **依赖/规模：** Phase 3；M；protocol、implementations、测试。

### P14-T02：实现 Eval Harness

- [ ] **描述：** 提供 FakeProvider 回归集和可选真实模型任务集。
- [ ] **验收：** 评测结果可重复，真实模型波动与代码回归分开报告。
- [ ] **验证：** deterministic eval smoke。
- [ ] **依赖/规模：** Phase 5、11；M；runner、cases、reporter、测试。

### P14-T03：建立 TypeScript 差分测试

- [ ] **描述：** 使用固定输入比较 stream、Agent events、ToolResult 和 Session projection。
- [ ] **验收：** 每个差异都有 documented disposition。
- [ ] **验证：** `pytest -m parity`。
- [ ] **依赖/规模：** 全部核心阶段；按契约族拆多个 M task。

### P14-T04：完成发布验收

- [ ] **描述：** 构建 wheel，从仓库外、全新 HOME 安装并运行完整 smoke matrix。
- [ ] **验收：** help/version/models/print/interactive/resume 可用，真实 DeepSeek 最小调用成功。
- [ ] **验证：** release script + 人工审查。
- [ ] **依赖/规模：** 所有前序任务；L，必须继续拆为 packaging/docs/smoke 三项。

## 阶段检查点

### Checkpoint A：P5 完成

- [ ] FakeProvider、DeepSeek、Agent Loop、七工具、print/json CLI 全部通过。
- [ ] 默认测试无网络、无凭据、无用户配置依赖。
- [ ] 从仓库外能执行第一条真实 tool-loop。

### Checkpoint B：P8 完成

- [ ] Session resume/fork/tree 和副作用幂等通过。
- [ ] Settings/AGENTS/Skills/Templates/Trust 可用。
- [ ] retry/compaction/branch summary 不破坏事件和 Session。

### Checkpoint C：P10 完成

- [ ] Extension 和 TUI 达到日常使用水平。
- [ ] Windows ConPTY 与 VirtualTerminal 双重验证通过。

### Checkpoint D：P14 完成

- [ ] 当前稳定 Pi 功能面均在 parity matrix 中有实现或明确的刻意差异。
- [ ] 未完成 Harness 保持 experimental，不影响稳定 CLI。
- [ ] 完整 Definition of Done 与人工审查通过。
