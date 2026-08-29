# pi-python

`pi-python` 是 Pi Coding Agent 的 Python 从零重写项目。行为基线来自本地上游源码
`D:\pi` 的冻结提交 `e14afc648e10fb6c527ea88fa627091ada764306`（Pi
`0.84.1`）。本项目复现行为、协议和兼容表，不复制 TypeScript 实现正文，也不做逐行翻译。

本文描述的是**当前源码的真实行为**。当文档与实际命令有差异时，按以下优先级判断：
当前源码与测试 > `pi-python --help` > 兼容矩阵 > 路线图 > 教程性文字。

## 1. 当前状态与能力边界

当前版本号是 `0.5.0`，主干能力推进到 Phase 11，并包含 checkpoint 之后的 TUI、工具组合和
Windows Git Bash 修复。它已经是一个可实际对话、调用工具、修改代码并保存会话的本地 Agent，
但 **Phase 12 的完整 CLI/RPC 和 Phase 13 的发布审查尚未完成，不能视为 1.0 或发布就绪版本**。

为了避免把“代码里已有”误写成“用户现在就能用”，能力分为三层：

| 层级 | 当前能力 | 如何使用 |
| --- | --- | --- |
| 默认 CLI/TUI | DeepSeek 对话、流式 thinking/text、`read`、`bash`、`edit`、`write`、持久化 v3 Session、regular/fullscreen TUI、文本附件、会话切换和分叉 | 直接运行 `pi-python` |
| SDK/内部可选 | 自定义 Provider/工具、七工具注册表、逐工具权限、压缩/分支摘要、资源/Extension/包管理底层、同步 SDK | Python API 显式注入并配置 |
| 尚未接入当前 CLI | `grep/find/ls` 默认注入、项目 trust 管理命令、包安装命令、`@file` 参数、HTML export、本地 JSONL RPC、远程 Session | Phase 12 或 Post-1.0 |

七个 Coding Tools 都有实现和契约测试，但默认 Agent 只创建四个：

```text
默认：read, bash, edit, write
可注入：grep, find, ls
```

`grep/find/ls` 需要调用方分别提供 `SearchOperations` 和 `FilesystemOperations`；仅仅导入
`create_all_tools()` 不会自动获得原生实现。

完整路线图见 [tasks/plan.md](tasks/plan.md)，原子任务见 [tasks/todo.md](tasks/todo.md)，
兼容范围见 [surface matrix](docs/compatibility/surface-matrix.md)。

## 2. 快速开始

### 2.1 环境要求

- Windows 或 Linux
- Python 3.12 或 3.13
- [uv](https://docs.astral.sh/uv/)
- DeepSeek API Key（真实模型对话需要）

```powershell
Set-Location D:\pi-python-claude
uv sync --frozen --all-groups
$env:DEEPSEEK_API_KEY = '你的 API Key'
uv run --frozen pi-python --tui-mode regular
```

### 2.2 让 Agent 操作另一个项目

Agent 把**启动进程时的当前目录**作为工作目录。更可靠的方式是先进入目标项目，再调用已经
安装好的可执行文件：

```powershell
Set-Location D:\other-project
& D:\pi-python-claude\.venv\Scripts\pi-python.exe --tui-mode regular
```

也可以安装为 uv tool：

```powershell
uv tool install --force D:\pi-python-claude
Set-Location D:\other-project
pi-python --tui-mode regular
```

### 2.3 Windows 的 Bash 选择

`bash` 工具需要 Bash，而不是 PowerShell。解析器依次考虑显式 `shellPath`、标准/相邻 Git Bash
和 PATH。若 Git 安装在非标准目录，例如 `D:\Git`，把下面内容保存到
`%USERPROFILE%\.pi-python\agent\settings.json`：

```json
{
  "shellPath": "D:\\Git\\bin\\bash.exe"
}
```

当前默认组合真实读取并传递的是 `shellPath`。设置模型还定义了其他未来字段，但不要据此假设
所有字段都已接入当前 CLI。

## 3. CLI 使用手册

先看本地真实 surface：

```powershell
pi-python --version
pi-python --help
pi-python --list-models
```

当前主要参数：

| 参数 | 作用 |
| --- | --- |
| `messages ...` | 有位置消息时执行一次 headless 对话；没有时进入交互 TUI |
| `--mode text\|json` | 输出最终文本，或输出 JSONL 事件流 |
| `--print` | 明确请求非交互执行，通常与位置消息一起使用 |
| `--tui-mode regular\|fullscreen` | 普通滚屏 TUI 或全屏 alternate-screen TUI |
| `--provider PROVIDER` | 选择 Provider；默认发行版当前内置 DeepSeek |
| `--model MODEL` | 选择模型；接受裸模型 id 或 `provider/model` 前缀形式（与 `--list-models` 输出一致） |
| `--thinking LEVEL` | `off/minimal/low/medium/high/xhigh/max`；DeepSeek 只支持 `off/high/max`，其余按最近支持级别钳制（`minimal/low/medium→high`，`xhigh→max`）。注意：实测当前 DeepSeek V4 API 在 `off` 下仍可能返回 reasoning 内容（请求侧已正确发送 `thinking: disabled`） |
| `--no-session` | 本轮不创建持久化 Session |
| `--session PATH` | 打开指定 Session |
| `--resume` | 选择并恢复 Session；交互模式下未指定 `--session-dir` 时自动使用默认 Session 目录 |
| `--continue` | 继续最近 Session；交互模式下未指定 `--session-dir` 时自动使用默认 Session 目录 |
| `--session-dir DIR` | 覆盖 Session 目录 |
| `--env-file FILE` | 从指定 dotenv 文件读取凭据 |

当前模型目录：

```text
deepseek/deepseek-v4-pro    默认
deepseek/deepseek-v4-flash
```

两者当前都声明为**文本输入**。图片附件虽然有格式和 10 MB 大小校验，但会因当前模型不支持
图片输入而被拒绝。Thinking 等级按模型能力钳制：`minimal/low/medium` 映射到 `high`，
`xhigh` 映射到 `max`。

### 3.1 Headless

```powershell
# 只打印最终 Assistant 文本
pi-python --print --no-session "只读分析项目入口、模块边界和测试方式，不要修改文件"

# 每行输出一个可独立解析的事件
pi-python --mode json --no-session "读取 README.md 并用三点概括项目"
```

JSON 模式会输出 Agent、消息、工具和流式状态事件；它不是 Phase 12 计划中的本地 RPC 协议。
工具事件带完整负载：`tool_execution_start`/`update`/`end` 分别包含 `toolCallId`、`toolName`、
`args`、`partialResult`/`result`（content 与 details）和 `isError`。

### 3.2 凭据和 Session 导入

DeepSeek 凭据优先级：

```text
显式 API key > 进程环境 DEEPSEEK_API_KEY > --env-file > 当前目录 .env
```

```powershell
pi-python auth check
pi-python auth check --json
pi-python auth print-api-key
pi-python import-pi-session D:\path\to\session.jsonl
```

`print-api-key` 会输出秘密，只应在私有终端使用。导入器先严格验证 v3 JSONL，再复制原始字节；
不会自动修复中间损坏，也不会重写源文件。缺少凭据时，请求会以明确消息失败
（`No credential configured for deepseek; set DEEPSEEK_API_KEY or provide an explicit API key`），
而不会伪装成通用请求错误。

## 4. TUI 交互能力

| 命令 | 作用 |
| --- | --- |
| `/help` | 显示命令帮助 |
| `/model` | 查看或切换模型 |
| `/thinking` | 查看或切换 thinking 等级 |
| `/attach PATH` | 把文本或受支持图片加入下一条用户消息 |
| `/copy` | 通过 OSC-52 复制最近 Assistant 文本 |
| `/sessions` | 列出当前项目 Session，并按编号切换 |
| `/fork` | 从当前持久化对话分叉新 Session |
| `/exit`、`/quit` | 退出 |

文本附件会以 UTF-8 全文嵌入下一条 UserMessage；当前没有文本附件大小上限，因此不要附加巨型
文件或秘密文件。

回合运行期间的键盘行为（真实控制台可用；管道输入自动降级为不可中断）：

- `Esc` 或 `Ctrl+C`：取消当前回合。回合以 aborted 结束，已生成的部分回答保留在屏幕上，
  并显示 `cancelled` 状态行；输入提示随后恢复。
- 直接输入一行并回车：作为 steering 消息插入当前 Agent 队列。若模型仍在工具链中，下一轮
  立即消费；否则在下一次发送提示时作为最前消息生效。屏幕显示 `steered: <文本>` 确认行。

恢复与切换：以 `--resume`/`--continue`/`--session` 启动，或在 `/sessions` 切换、`/fork` 分叉后，
已恢复的历史消息会按原样式重放到当前 transcript（用户消息带 `> ` 前缀，含 thinking 摘要与
工具结果行），无需依赖记忆提问。

- `regular`：保留 scrollback，只重绘活动块；Windows 下按终端宽度减一列，避免右边界自动
  换行造成重复和覆盖。
- `fullscreen`：进入 alternate screen，按当前行列裁剪并整屏重绘；退出后恢复原终端。

渲染器处理 ANSI、CJK 双宽字符、流式修订、长行换行和工具错误摘要。普通模式适合保留历史；
全屏模式适合固定窗口，但历史查看受屏幕高度限制。

## 5. 整体架构

### 5.1 包依赖边界

```text
pi_telemetry  <-  pi_ai  <-  pi_agent
      ^             ^          ^
      +-------------+----------+

pi_tui  （独立，不导入其他 pi_* 包）
      ^
      |
pi_coding_agent  （唯一产品组合层，组合以上所有包）
```

| 包 | 职责 | 明确不负责 |
| --- | --- | --- |
| `pi_telemetry` | span/event/status 协议、No-op 与内存实现 | 模型、Session、UI |
| `pi_ai` | 消息/content、模型、Provider 协议、AssistantStream、DeepSeek wire/schema、FakeProvider | Agent 循环、文件工具 |
| `pi_agent` | Agent 状态、事件、核心循环、工具调度、steering/follow-up、取消 | Session 文件、CLI、具体 Provider |
| `pi_tui` | 通用终端应用、布局、编辑器、历史、补全、按键、组件、主题、终端适配和渲染 | 业务 Agent 或 Provider |
| `pi_coding_agent` | 设置、服务、资源、Extension、工具、Session、SDK、CLI、产品 TUI | 无；它是 composition root |

关键入口：

- CLI：[src/pi_coding_agent/cli/main.py](src/pi_coding_agent/cli/main.py)
- SDK：[src/pi_coding_agent/sdk.py](src/pi_coding_agent/sdk.py)
- AgentSession：[src/pi_coding_agent/agent_session.py](src/pi_coding_agent/agent_session.py)
- Agent 核心：[src/pi_agent/agent.py](src/pi_agent/agent.py)
- Agent loop：[src/pi_agent/loop.py](src/pi_agent/loop.py)
- DeepSeek：[src/pi_ai/providers/deepseek/provider.py](src/pi_ai/providers/deepseek/provider.py)
- 工具注册：[src/pi_coding_agent/tools/registry.py](src/pi_coding_agent/tools/registry.py)
- 资源加载：[src/pi_coding_agent/resources/default_loader.py](src/pi_coding_agent/resources/default_loader.py)
- 产品 TUI：[src/pi_coding_agent/tui](src/pi_coding_agent/tui)
- v3 Session：[src/pi_coding_agent/session](src/pi_coding_agent/session)

## 6. 一次请求的完整执行流程

```text
用户输入
  -> CLI 参数分流
  -> 凭据/模型/Session/服务初始化
  -> 资源发现与系统提示组装
  -> AgentSession.prompt()
  -> Agent 核心循环
  -> DeepSeek 流式响应
  -> thinking/text/tool-call 事件
  -> 工具校验、调度与执行
  -> ToolResult 回填上下文
  -> 下一轮模型调用，直到最终回答
  -> v3 JSONL 持久化
  -> TUI 渲染或 headless 输出
```

### 6.1 CLI 和运行时组合

console script `pi-python` 进入 `pi_coding_agent.cli.main:main`。首个有效参数是 `auth` 或
`import-pi-session` 时进入命令解析器；有位置消息时 headless；没有位置消息时进入 TUI。

`create_agent_session()` 随后：

1. 解析 cwd，创建或打开该项目的 SessionManager。
2. 创建 settings、project trust、资源、Extension 等 ProductServices。
3. 创建 DeepSeek ModelRuntime，或使用调用方注入的运行时。
4. 恢复已有 Session 的消息、模型和 thinking。
5. 从全局 settings 读取 `shellPath`。
6. 默认创建 `read/bash/edit/write`，再合并可信启动的 Extension tools。
7. 如提供 PermissionGate，则在工具外包一层权限判定。
8. 组合系统提示、模型、工具和恢复消息，构造 Agent 与 AgentSession。

切换或 fork 时，旧服务/Extension 会关闭，再按新 cwd 和 Session 重建，避免旧项目资源泄漏。

### 6.2 系统提示、trust 和资源

提示由产品默认提示、cwd、全局资源，以及**可信项目**的 `SYSTEM.md`、`AGENTS.md`/
`CLAUDE.md`、skills 描述等组合。未知项目默认不可信：项目级 `.pi-python` 资源、上下文和
Extension 不会直接激活。当前 CLI 还没有 trust 管理命令；trust store/API 已存在，主要供
SDK 和后续 CLI 使用。

Skill 只把名称、描述和位置注入固定上下文，正文按需用读取工具加载，避免长期占满上下文。
Extension manifest 枚举不执行代码；只有精确 manifest/entry 身份获得运行时 trust 后才激活。

### 6.3 Provider 流

DeepSeek Provider 使用 OpenAI-compatible streaming chat completions：

1. 把系统、用户、Assistant、ToolResult 编码为 wire messages。
2. 把工具参数模型编码为 JSON Schema。
3. 把增量响应转换为 thinking、text、tool-call 事件。
4. `AssistantStream` 验证顺序并限制为单消费者。
5. Agent 更新状态，TUI/JSON presenter 同步接收事件。

Provider 默认不做底层自动重试。产品层对可重试错误最多重试三次，采用 2/4/8 秒退避；
Provider 请求重试和 AgentSession 整轮重试是独立、可观察的层次。

### 6.4 工具循环

当模型给出 tool call：

1. 按 Pydantic schema 严格校验参数。
2. 执行 before hook 和可选权限判断。
3. 调度工具；独立调用可并行，同一路径的 `edit/write` 通过 mutation queue 串行化。
4. 流式发送 Bash 输出等更新。
5. 生成 ToolResult；失败也会成为清理后的可见结果。
6. 把 ToolResult 加入上下文，再次请求模型。
7. 到普通答案、取消、错误、终止信号或 100 turns 上限时结束。

底层 Agent 还有 steering 和 follow-up 队列；当前简单 TUI 没有单独暴露专用命令。

### 6.5 Session

AgentSession 把完成的 User、Assistant 和 ToolResult 写入 append-only v3 JSONL：

- 默认目录：`%USERPROFILE%\.pi-python\agent\sessions\--<编码后的 cwd>--`；
- entry 使用 id/parentId，既能恢复活动路径，也能表达分支树；
- 首个 Assistant 出现前延迟创建文件，避免未完成输入留下空会话；
- append 后 fsync，支持的平台上权限收紧为 `0600`；
- 严格读取，失败时保留原字节，不自动修复中间损坏；
- 未配对旧 Tool Call 只补合成错误结果，绝不重新执行；
- fork 原子复制所选活动路径，并记录父 Session。

CompactionService 和 BranchSummaryService 已实现，但默认 CLI 没有 summarizer，因此不自动启用。
SDK 必须显式传入 `compaction_summarizer` 或 `branch_summarizer`。

## 7. 功能明细

### 7.1 默认工具

| 工具 | 行为 | 限制 |
| --- | --- | --- |
| `read` | UTF-8 读取、offset/limit；最多返回 2000 行或 50 KB，并给 continuation | 非 UTF-8 无损编辑不是默认保证 |
| `bash` | Git Bash、取消、超时、进程组终止、合并输出、流式更新；尾部截断 2000 行/50 KB，完整输出写临时日志 | Windows 必须解析到可用 Git Bash |
| `edit` | 唯一、精确、非重叠替换，原子落盘，同文件修改串行化 | 匹配缺失或不唯一会失败，不模糊猜测 |
| `write` | 原子写入完整 UTF-8 文件并创建父目录 | 是整文件写入，不是 append |

路径支持相对路径、绝对路径、`~` 和兼容 `@` 前缀；**不会限制在 cwd 内**。

### 7.2 可注入工具与 SDK

| 工具 | 行为 | 所需端口 |
| --- | --- | --- |
| `grep` | 内容搜索、稳定排序，默认 100 条/50 KB | `SearchOperations` |
| `find` | 路径搜索、稳定排序，默认 1000 条/50 KB | `SearchOperations` |
| `ls` | 目录项稳定、大小写不敏感排序 | `FilesystemOperations` |

注入形态如下；两个 operations 必须由集成方实现：

```python
from pathlib import Path

from pi_coding_agent.sdk import CreateAgentSessionOptions, create_agent_session
from pi_coding_agent.tools import create_all_tools

tools = create_all_tools(
    cwd=Path.cwd(),
    search_operations=search_ops,
    filesystem_operations=filesystem_ops,
)
created = await create_agent_session(
    CreateAgentSessionOptions(cwd=Path.cwd(), tools=tools)
)
try:
    await created.session.prompt("分析项目")
finally:
    await created.close()
```

异步 SDK 还可注入 ModelRuntime、CredentialResolver、SessionManager、系统提示、thinking、
PermissionGate、时钟/id/时间工厂以及两个 summarizer；同步包装在
`pi_coding_agent.sync_sdk`。项目包含 `rg`/`fd` 固定版本、SHA-256 校验下载管理器，但这不等于
默认 CLI 已自动把它们装配为 `SearchOperations`。

### 7.3 其他已实现底层

- Extension registry：工具、命令、Provider、flag、shortcut；启动/关闭失败隔离。
- prompts/skills/themes 描述器已实现；当前 TUI 没有完整 prompt/theme 选择命令。
- `.pi` 兼容适配器只读 prompts/skills/themes/sessions，明确跳过 JS/TS Extension。
- 包底层支持本地/git/PyPI 规格、uv 托管环境、原子 lock/rollback，以及阻止脚本和危险路径的
  npm data-only 提取；当前 CLI 没有包管理命令。
- `pi_telemetry` 有稳定协议、No-op 和内存实现；默认 CLI 没有外部 exporter。
- FakeProvider、假操作端口和可注入时钟用于离线确定性测试。

## 8. 安全边界

这是宽权限本地 Coding Agent，不是 sandbox：

- 文件工具可访问当前账户有权访问的 cwd 外绝对路径；
- Bash 可执行当前账户允许的命令；默认 PermissionGate 关闭；
- project trust 控制项目资源/Extension，不等于限制文件工具权限；
- 文本附件没有大小上限；不要附加密钥或巨型文件；
- 推荐在新 Git 仓库、临时目录、容器或可丢弃副本中测试，每轮后检查 `git diff`；
- live Provider 调用会联网并可能产生费用，默认测试不会运行它。

详见 [威胁模型](docs/security/threat-model.md) 与 [SECURITY.md](SECURITY.md)。

## 9. 真实完整对话测试

下面创建一个**故意带真实 bug** 的小型库存项目，用来测试读取、Bash、诊断、精确编辑、创建
文件、测试驱动修改、长流式输出、Session、fork、附件和 headless。不要在重要仓库里做实验。

### 9.1 创建一次性实验项目

```powershell
$lab = 'D:\pi-agent-lab'
if (Test-Path -LiteralPath $lab) {
    throw "$lab 已存在；请人工确认后换新目录，避免覆盖数据。"
}
New-Item -ItemType Directory -Path "$lab\src\stockroom" -Force | Out-Null
New-Item -ItemType Directory -Path "$lab\tests" -Force | Out-Null

@'
"""Small inventory domain used for agent testing."""

def available(stock: int, reserved: int) -> int:
    if stock < 0 or reserved < 0 or reserved > stock:
        raise ValueError("invalid inventory state")
    return stock - reserved

def receive(stock: int, quantity: int) -> int:
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    return stock - quantity  # Intentional bug: delivery should increase stock.
'@ | Set-Content -LiteralPath "$lab\src\stockroom\inventory.py" -Encoding utf8

@'
from .inventory import available, receive
__all__ = ["available", "receive"]
'@ | Set-Content -LiteralPath "$lab\src\stockroom\__init__.py" -Encoding utf8

@'
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from stockroom.inventory import available, receive

class InventoryTests(unittest.TestCase):
    def test_available_subtracts_reserved(self) -> None:
        self.assertEqual(available(10, 3), 7)

    def test_invalid_state_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            available(2, 3)

    def test_receive_increases_stock(self) -> None:
        self.assertEqual(receive(10, 3), 13)

if __name__ == "__main__":
    unittest.main()
'@ | Set-Content -LiteralPath "$lab\tests\test_inventory.py" -Encoding utf8

@'
# Stockroom lab

Run tests: `python -m unittest discover -s tests -v`

Rules: inventory values are integers; values cannot be negative; deliveries and
transfers must use positive quantities.
'@ | Set-Content -LiteralPath "$lab\README.md" -Encoding utf8

git -C $lab init
git -C $lab add .
git -C $lab status --short
```

```powershell
Set-Location D:\pi-agent-lab
$env:DEEPSEEK_API_KEY = '你的 API Key'
& D:\pi-python-claude\.venv\Scripts\pi-python.exe --tui-mode regular
```

### 9.2 任务一：只读架构与 bug 诊断

> 完整读取这个项目，说明入口、模块职责、数据流和测试方法。然后实际运行测试，定位失败的
> 根因，给出文件和符号证据。本轮只分析，不修改任何文件。不要根据 README 猜测源码行为。

预期：调用 `read/bash`；三项测试中 delivery 失败；指出 `receive()` 使用减法；diff 为空。

### 9.3 任务二：最小修复

> 修复刚才确认的 receive bug。先保留失败证据，只做最小改动，然后运行完整 unittest。
> 检查 git diff，说明改了什么、为什么，没有顺手重构其他代码。

预期：使用 `edit` 把减法改为加法，全部测试通过，只有一处业务表达式改变。

### 9.4 任务三：测试驱动新增功能

> 新增 `transfer(source_stock: int, target_stock: int, quantity: int) -> tuple[int, int]`。
> quantity 必须为正，来源库存必须足够；失败时抛 ValueError。先添加成功、数量非正、库存不足
> 的测试并确认新测试失败，再写最小实现。更新公开导出，运行完整测试并审查 diff。

预期：修改实现、测试和 `__init__.py`，展示红灯到绿灯的证据。

### 9.5 任务四：创建真实 CLI

> 新增 `src/stockroom/cli.py`，支持
> `python -m stockroom.cli transfer --source 10 --target 3 --quantity 4`。成功时 stdout 输出
> 单行 JSON `{"source": 6, "target": 7}` 并返回 0；领域校验失败时 stderr 输出清晰错误并
> 返回非 0。只用标准库。新增 subprocess 测试，先失败后实现，运行全部测试，并更新 README。

预期：`write` 创建新文件，`edit` 更新现有文件，Bash 验证成功与失败路径。

### 9.6 任务五：只读审查

> 停止实现。完整审查 staged 和 unstaged diff，按严重度列出 correctness、边界条件、安全性、
> 可维护性和测试缺口。每条必须引用具体文件和代码；没有阻断问题就明确说没有，不要虚构。
> 本轮不得修改文件。

### 9.7 任务六：Session 与 fork

1. `/exit` 后在同一目录重启。
2. 输入 `/sessions`，选择刚才 Session。
3. 问：`总结已经完成的任务，并读取当前源码验证，不要只依赖历史回答。`
4. 输入 `/fork`。
5. 问：`如果 transfer 改为返回 dataclass，列迁移方案但不要修改。`

预期：消息和模型设置恢复；fork 创建新 Session，新讨论不回写原 Session。

### 9.8 任务七：附件

```text
/attach README.md
只根据附件提取明确规则，再读取源码判断文档是否过时。分别标注“附件声明”和“源码证据”。
```

预期：附件进入下一条 UserMessage，Agent 仍使用 `read` 做交叉验证。

### 9.9 任务八：Bash、错误与长流式渲染

依次发送：

> 使用 bash 实际运行 `pwd`、`git --version` 和 Python 版本检查，原样概括结果。

> 使用 bash 运行确定不存在的命令 `pi-python-command-that-must-not-exist`。不要规避执行；解释
> 退出状态和错误摘要，不要把失败伪装成成功。

> 用不少于 20 个编号步骤详细解释输入如何经过 CLI、Agent、Provider、工具循环、Session 和
> TUI。每步单独一行且包含较长中文说明，用于测试 regular 模式滚动和长行换行。

预期：选择可用 Git Bash；工具失败摘要可见；长 thinking/answer 不重复覆盖，下一轮输入提示
在新行。若仍有视觉问题，用 fullscreen 对照并记录终端类型、窗口宽高和最小复现文本。

### 9.10 任务九：Headless 与 JSONL

```powershell
Set-Location D:\pi-agent-lab
$pi = 'D:\pi-python-claude\.venv\Scripts\pi-python.exe'
& $pi --print --no-session '只读检查库存项目当前架构和测试状态，用五点回答，不修改文件'
& $pi --mode json --no-session `
  '读取 src/stockroom/inventory.py，说明公开函数，不修改文件' |
  Set-Content -LiteralPath .\agent-events.jsonl -Encoding utf8
Get-Content -LiteralPath .\agent-events.jsonl -TotalCount 5
```

预期：第一条只有最终文本；第二条每行可独立解析为 JSON，包含消息、工具和流式事件。

### 9.11 不调用真实模型的验证

这些测试使用 FakeProvider/假操作端口，验证七工具注册、Agent 工具循环、Session 和 TUI：

```powershell
Set-Location D:\pi-python-claude
uv run --frozen pytest `
  tests/pi_coding_agent/tools/test_registry.py `
  tests/pi_agent/test_loop_tools.py `
  tests/pi_coding_agent/agent_session/test_basic.py `
  tests/pi_coding_agent/tui -q
```

## 10. 开发与验证

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

pytest 会切换到临时 HOME/cwd、清除常见 credential，并阻断 Python 网络、Python 子进程和
常见网络客户端。它不是 OS 防火墙；原生二进制 raw socket 只能由隔离 runner 保证。不要为
离线测试复制真实 `.env`。任何 live DeepSeek smoke test 都需操作者明确选择运行。

## 11. 上游 oracle

不得对上游 `D:\pi` 运行会格式化、生成或写回文件的脚本。

```powershell
$env:PI_TS_SOURCE = 'D:\pi'
uv run --frozen python scripts/ts_oracle.py --source D:\pi verify
```

预期 commit 是 `e14afc648e10fb6c527ea88fa627091ada764306`。

## 12. 已知未完成项

- Phase 12 完整 CLI、`@file`/多模态参数、HTML export、trust/package 命令、本地 JSONL RPC；
- 远程 Session、Harness、SQLite、lanes（Post-1.0）；
- Phase 13 跨平台安装、许可、发布和最终验收；
- macOS 在当前 1.0 compatibility scope 中明确不支持。

## 13. 许可状态

本仓库原创 Python 代码当前未授予开源许可，不提供根 `LICENSE`。上游 Pi 材料的版权和完整
MIT 许可文本见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
