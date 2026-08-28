# pi-python

`pi-python` 是 Pi Coding Agent 的 Python 从零重写项目。行为基线来自本地上游源码 `D:\pi` 的冻结提交 `e14afc648e10fb6c527ea88fa627091ada764306`（Pi `0.84.1`）；本项目复现行为和协议，但不复制 TypeScript 实现正文，也不做逐行翻译。

## 当前状态

项目当前已完成 **Phase 11 / 0.5.0 checkpoint**：Agent、DeepSeek Provider、v3 Session、CLI/SDK、Extension/资源加载、七个 Coding Tools 和 regular/fullscreen TUI 均已实现。默认 SDK、CLI 和 TUI 启用上游一致的 `read`、`bash`、`edit`、`write` 编码工具，并把当前工作目录及可信的 `SYSTEM.md`、`AGENTS.md`、skills 组合进 Agent 提示。

Phase 12 的完整 CLI/RPC/HTML export 和 Phase 13 的发布审查尚未完成；当前状态不能等同于 1.0 发布就绪。

完整路线图见 [tasks/plan.md](tasks/plan.md)，原子任务见 [tasks/todo.md](tasks/todo.md)，兼容范围见 [surface matrix](docs/compatibility/surface-matrix.md)。

## 架构边界

```text
pi_telemetry  ←  pi_ai  ←  pi_agent
       ↑            ↑          ↑
       └────────────┴──────────┤
pi_tui  ───────────────────────┤
                               ↓
                       pi_coding_agent
```

- `pi_telemetry`：Telemetry 协议和实现。
- `pi_ai`：消息、模型、Provider、流和工具 schema。
- `pi_agent`：Agent 状态、事件和核心循环。
- `pi_tui`：不依赖 Agent/AI 的通用终端 UI。
- `pi_coding_agent`：Session、工具、资源、Extension、CLI、SDK 和产品 TUI 的组合层。

这些包边界已经落地，产品组合只发生在 `pi_coding_agent`。

## 使用

在希望 Agent 操作的项目目录中启动：

```powershell
$env:DEEPSEEK_API_KEY = '你的 API Key'
uv run --frozen pi-python --tui-mode regular
```

进入后可直接要求它分析当前项目；默认工具能够读取和修改 cwd 下的文件。无头调用使用 `--print`，事件流使用 `--mode json`。完整参数以当前安装的 `pi-python --help` 为准。

## 开发环境

要求：

- Windows 或 Linux
- Python 3.12 或 3.13
- [uv](https://docs.astral.sh/uv/)

```powershell
uv sync --frozen --all-groups
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen pyright
uv run --frozen pytest tests -m "not live_provider and not network"
uv build --no-sources
uv run --frozen python scripts/check_surface_matrix.py --source D:\pi
uv run --frozen python scripts/verify_distribution.py
uv run --frozen pip-audit --local
```

pytest 会在收集测试前切换到临时 HOME/cwd、清除常见 credential，并阻断 Python
网络、Python 子进程和常见网络客户端。该门禁不是 OS 防火墙；任意原生二进制的
raw socket 只能由隔离 runner 保证。不要为了运行离线测试复制真实 `.env`。

## 上游源码 oracle

oracle 只执行明确允许的只读检查；不得对上游运行会格式化、生成或写回文件的脚本。

```powershell
$env:PI_TS_SOURCE = 'D:\pi'
uv run --frozen python scripts/ts_oracle.py --source D:\pi verify
```

预期 commit 必须是 `e14afc648e10fb6c527ea88fa627091ada764306`。

## DeepSeek 配置

DeepSeek Provider 已实现，凭据优先级为：

```text
--api-key > 进程环境 > --env-file > 当前工作目录 .env
```

`.env.example` 只包含无效占位值。任何真实 API smoke test 都必须在当次执行前取得用户批准。

## 兼容与安全边界

- 正式支持 Windows/Linux；macOS 在 1.0 中明确不支持。
- 默认保持 Pi 的宽工具权限，不提供核心 sandbox；逐工具权限是默认关闭的 Extension。
- `.pi/` 仅在显式兼容模式下只读使用，不执行 JS/TS Extension。
- 本地 JSONL RPC 属于 1.0；远程 Session、Harness、SQLite、lanes 属于 Post-1.0。

详见 [威胁模型](docs/security/threat-model.md) 与 [SECURITY.md](SECURITY.md)。

## 许可状态

本仓库原创 Python 代码当前未授予开源许可。项目不提供根 `LICENSE`。上游 Pi 材料的版权和完整 MIT 许可文本见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
