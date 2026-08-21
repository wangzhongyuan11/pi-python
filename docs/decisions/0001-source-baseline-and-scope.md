# ADR 0001：冻结源码基线与 Python 1.0 范围

- 状态：Accepted
- 日期：2026-08-15
- 决策者：Pi Python 重写项目

## 背景

Pi 的公开教程、README 和当前仓库并不处在同一版本。若按教程示例直接翻译，会把旧架构、示意代码和当前实现混为一谈。与此同时，冻结仓库里既有成熟的 Coding Agent 路径，也有 Harness、SQLite Session 后端、CBOR protocol/client/server 等实验路径。

本项目需要一个在整个 1.0 周期内不漂移的事实基线，并明确什么是兼容目标、什么是有意分歧、什么延后实现。

## 决策

1. 唯一第一权威是本机 `D:\pi` 的提交 `e14afc648e10fb6c527ea88fa627091ada764306`，上游版本为 `0.84.1`。
2. 源码与测试共同定义行为；README、注释和教程只在不与源码/测试冲突时解释动机。
3. [Pi Agent 教程](https://dg-ai-notes.pages.dev/modules/) 只作为概念讲解材料。教程中的 Python 代码不作为可执行规范，也不用于反推冻结提交不存在的接口。
4. 采用 from-scratch behavioral reimplementation：直接阅读上游源码以复现公开行为、wire schema、调用顺序和模块边界，但不复制上游实现正文；不宣称未接触源码的独立实现。
5. Python 1.0 兼容目标是成熟的产品链：

   ```text
   CLI / SDK / local JSONL RPC / TUI
   -> AgentSessionRuntime
   -> AgentSession
   -> Agent
   -> Agent Loop
   -> Provider / Tool
   -> v3 SessionManager
   ```

6. Python 1.0 必须包含 DeepSeek Provider、核心 Agent Loop、七个 Coding Tools、同步 v3 Session、异步 SDK 与同步便利层、CLI text/JSON/TUI、本地 stdin/stdout JSONL RPC、Settings/Resource/Skill/Prompt/Theme、Python-native Extension 和 project trust。
7. 下列能力不进入 1.0：Harness operation records/lanes/v4 repository、SQLite Session 后端、远程 CBOR protocol/client/server、Node sidecar、JS/TS Extension 执行、内建多 Provider/OAuth、终端图片协议和 macOS。
8. 所有兼容表条目只能使用 `Supported`、`Intentional divergence`、`Post-v1` 三种状态；定义见 [ADR 0003](0003-compatibility-divergence-and-session-recovery.md)。

## 源码证据

- 根 workspace 同时收纳普通 packages 与 session backends：`D:\pi\package.json:L5-L9 @ e14afc648`。
- `pi-ai`、`pi-agent-core`、`pi-tui`、`pi-coding-agent` 均为 `0.84.1`：`D:\pi\packages\ai\package.json:L2-L3`、`packages\agent\package.json:L2-L3`、`packages\tui\package.json:L2-L3`、`packages\coding-agent\package.json:L2-L3 @ e14afc648`。
- Coding Agent 的稳定公开入口包含主 SDK、`rpc-entry` 和 remote `client` 子路径：`D:\pi\packages\coding-agent\package.json:L9-L24 @ e14afc648`。
- `pi-server` 自己标记为 experimental：`D:\pi\packages\server\package.json:L2-L4 @ e14afc648`。
- 成熟 SessionManager 明确使用 v3、JSONL append-only tree：`D:\pi\packages\coding-agent\src\core\session-manager.ts:L30-L156,L845-L855 @ e14afc648`。
- `pi-agent-core` 主入口同时导出核心 Agent 与 Harness，因此不能把“package 公开导出”误当成“产品 1.0 必做”：`D:\pi\packages\agent\src\index.ts:L1-L18,L25-L73 @ e14afc648`。

## 备选方案

### 跟随上游 main

拒绝。上游变化会让兼容矩阵和差分测试失去稳定预期。

### 只按教程实现

拒绝。教程版本较旧，且未覆盖当前 Extension、Session、RPC 和实验远程栈的完整表面。

### 1.0 一次实现全部 workspace package

拒绝。实验栈会显著增加恢复语义、传输协议和后端一致性风险，却不能更早证明核心 coding-agent 链路。

## 结果

- 好处：每个兼容结论都能回指固定源码；阶段验收不会因上游变化失效。
- 代价：冻结后出现的上游修复不会自动进入 Python 1.0，必须通过独立 ADR、测试和变更记录引入。
- 约束：任何人改变范围或冻结提交前，必须先更新本 ADR、surface matrix 和受影响契约。
