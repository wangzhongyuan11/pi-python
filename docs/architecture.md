# pi-python 架构

本文描述当前源码的真实架构。模块边界由 `tests/test_import_boundaries.py` 强制,
公共表面由 `docs/compatibility/surface-matrix.md` 枚举。

## 1. 包结构与依赖方向

```text
pi_telemetry   遥测协议(No-op / 内存实现),不依赖其他 pi_* 包
pi_ai          消息/模型/Provider 流/编解码;只依赖 pi_telemetry
pi_agent       Agent 状态机、事件、循环、五阶段工具管线;依赖 pi_ai
pi_tui         通用终端组件(不依赖任何 pi_* 产品包)
pi_coding_agent 唯一产品组合层:CLI/TUI/SDK/RPC、会话、工具、资源、扩展、导出
```

方向测试保证:`pi_tui` 不反向依赖产品包;`pi_coding_agent` 内部模块对同包
一律相对导入。

## 2. 一个回合的执行路径

1. 入口(`cli/main.py` / `tui/runner.py` / `sdk.py` / `rpc/runner.py`)调用
   `create_agent_session`,由 `AgentSessionRuntime` 按代际构建 cwd 绑定的
   全部服务(Settings、ResourceLoader、ExtensionRuntime、Exporter)。
2. `pi_agent.Agent` 组装 LLM 上下文:扩展 `context` hook 先改写消息序列,
   再由两阶段转换转换为 Provider 消息。
3. Provider 流(pi_ai)产出 12 类有序事件;`before_provider_request` /
   `before_provider_headers` hook 可改写出站载荷。
4. 工具调用进入五阶段管线(prepare → validate → before hook → execute →
   after hook),并行结果按模型顺序回填;扩展 `tool_call`/`tool_result`
   hook 可阻断、改写参数或改写结果。
5. 会话以 append-only JSONL(v3)持久化;扩展插入的消息排队到
   ToolCall/ToolResult 配对闭合之后,绝不拆开配对。
6. 阈值触发的自动压缩生成增量摘要;压缩切点不会拆开工具调用对。

## 3. 双运行时扩展

- **Python 扩展**:`pi-extension.json` + `main.py`,由两阶段 loader
  (trust 前只枚举,trust 后才 import)激活,注册 Tool/Command/Flag/
  Shortcut/Provider/renderer。
- **TypeScript 扩展**:上游风格 `*.ts` 由托管 Node 进程
  (`node/extension-host/`)经 type-stripping/Jiti 加载。两侧通过 JSONL
  stdio 协议 v1 通信:注册面代理进 Python registry,函数留在 Node 侧经
  `execute_tool`/`run_command` 回调;事件经共享 HookRunner 有序转发;
  UI 走可序列化子集(input/confirm/select/notify),JS 渲染器与自定义
  Provider 报告为 unsupported。宿主生命周期受监督:reload 换代、崩溃记
  诊断、关闭无孤儿进程。

## 4. 会话与资源

- 会话文件是严格 v3 JSONL;读取为纯读、损坏按行报告;`session repair`
  只截断损坏尾行;fork 复制活动路径;`import-pi-session` 只读上游 `.pi`。
- 资源发现按 显式 → 项目(trust)→ 全局 → 内建 → 已安装包 的优先序产出
  descriptor;项目资源只在 canonical trust 之后生效。
- 包管理支持 本地/Git/PyPI/npm 四类来源;npm 包零脚本执行,数据资源直接
  进入发现层。

## 5. 四入口共享一个组合根

`bootstrap.create_product_services` 是唯一的服务组合点;CLI、TUI、SDK、
RPC 四个入口经过同一 runtime factory,因此 Settings、资源、工具与扩展的
可观察行为一致(由 `test_bootstrap_parity` 证明)。会话替换(new/resume/
fork/switch)按代际重建全部 cwd 绑定服务并 teardown 旧代际。

## 6. 可靠性机制

- Provider 请求重试与会话轮级重试(2/4/8s,最多三次)分层可观测。
- 上下文溢出触发至多一次恢复;扩展插入消息排队等配对闭合。
- 扩展 `exec` 子进程登记在运行时内,关闭/换代时终止。
- 包安装、扩展加载、hook 异常、RPC 断连、损坏会话替换五类故障均隔离,
  产品保持可用(`test_failure_recovery`)。
- 语义差分 oracle(`scripts/differential_oracle.py`)证明会话树与压缩
  切点算法与冻结上游一致。

## 7. 已知边界(截至本文)

- MCP(Phase 18)、子代理/后台任务(Phase 19)、worktree 运行时
  (Phase 20)尚未实现。
- 附件跨模式契约已统一(CLI `@file`、TUI `/attach`、SDK 消息、RPC 拒绝
  argv 附件);HTML 导出转义优先。
- TypeScript 扩展的自定义 TUI 组件与自定义 Provider 属于结构性 unsupported
  (无法跨进程序列化),由安装检查显式报告。
