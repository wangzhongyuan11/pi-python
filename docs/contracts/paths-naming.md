# 路径、命名与配置发现契约

## 1. 产品与 Python 名称

| 对象 | 固定名称 |
|---|---|
| distribution | `pi-python` |
| console script | `pi-python` |
| Python packages | `pi_telemetry`, `pi_ai`, `pi_agent`, `pi_tui`, `pi_coding_agent` |
| 全局配置根 | `~/.pi-python/agent` |
| 项目配置根 | `<cwd>/.pi-python` |
| 上游兼容根 | `<cwd>/.pi`，默认忽略，只在显式 compatibility/import 模式只读 |

命名分歧避免覆盖已安装的上游 `pi`。上游名称和目录来自 `D:\pi\packages\coding-agent\package.json:L6-L11 @ e14afc648`。

## 2. 环境变量

| 名称 | 含义 | 优先级 |
|---|---|---|
| `PI_PYTHON_AGENT_DIR` | 覆盖全局配置根 | 高于默认 home |
| `PI_PYTHON_SESSION_DIR` | 覆盖 Session 存储目录 | 低于 CLI `--session-dir`，高于 settings |
| `PI_PYTHON_OFFLINE` | 禁止启动网络操作 | CLI `--offline` 与其任一为真即启用 |
| `DEEPSEEK_API_KEY` | DeepSeek credential | 低于 CLI key，高于 `.env` |

不使用包含连字符的动态环境名。上游会从 APP_NAME 动态构造 agent/session 环境变量（`D:\pi\packages\coding-agent\src\config.ts:L488-L496 @ e14afc648`）；Python 固定名称以保证 shell 可移植性。

## 3. Credential 与 `.env`

DeepSeek key 的解析顺序固定为：

```text
本次 --api-key
-> 已存在的进程 DEEPSEEK_API_KEY
-> --env-file 指定文件
-> <final runtime cwd>/.env
-> CredentialError
```

- `.env` 只读，不写回、不搜索祖先目录、不自动放入 `os.environ`。
- `--env-file` 相对路径按启动 cwd 解析；Session 切换 cwd 不改变显式文件。
- 仅解析 `DEEPSEEK_API_KEY`；不执行 command substitution、不展开 shell、不接受 `export $(...)`。
- key 只进入 Provider request 的内存 credential，不进入 Session、Settings、Tool env、RPC state 或日志。
- Python 1.0 不创建 `auth.json`。

上游 DeepSeek 环境名证据：`D:\pi\packages\ai\src\env-api-keys.ts:L88-L123 @ e14afc648`；上游 `--api-key` 入口：`D:\pi\packages\coding-agent\src\cli\args.ts:L70-L84 @ e14afc648`。

## 4. 全局布局

```text
~/.pi-python/agent/
├── settings.json
├── keybindings.json
├── trust.json
├── models.json
├── sessions/
│   └── --encoded-cwd--/
│       └── <timestamp>_<session-id>.jsonl
├── extensions/
├── skills/
├── prompts/
├── themes/
├── packages/
└── cache/
```

- `settings.json` 与 `keybindings.json` 是用户可编辑配置。
- `trust.json` 只由 trust store 在锁内、原子写入。
- `models.json` 是目录缓存，不含 credential。
- `packages/` 存放已解析的 Python Extension source/isolated env metadata；锁文件记录不可变版本/commit/hash。
- `cache/` 可删除，不承载唯一状态。

上游同类路径集中于 agent dir：`D:\pi\packages\coding-agent\src\config.ts:L511-L565 @ e14afc648`。

## 5. 项目布局与信任

```text
<cwd>/.pi-python/
├── settings.json
├── extensions/
├── skills/
├── prompts/
├── themes/
├── SYSTEM.md
└── APPEND_SYSTEM.md
```

ancestor `AGENTS.override.md`、`AGENTS.md`、`CLAUDE.md` 和 `.agents/skills/` 也属于项目资源。任何项目资源在 project trust 决策前都不加载；`--approve` 只表示“本次信任项目资源”，不表示批准每个 Tool Call。

冻结源码的 trust-requiring 列表和 project resource roots：`D:\pi\packages\coding-agent\src\core\trust-manager.ts:L27-L36,L179-L207`、`packages\coding-agent\src\core\resource-loader.ts:L812-L821 @ e14afc648`。

## 6. Settings 合并与路径基准

```text
内建默认值
< 全局 settings
< 可信项目 settings
< 环境变量
< CLI override
```

- 未信任时项目 settings 完全不参与 merge。
- 全局 settings 中的相对资源路径相对全局 agent dir；项目 settings 中的相对路径相对 cwd；CLI 相对路径相对启动 cwd。
- Session resume/switch 先确定 Session header cwd，再重建 cwd-bound Settings、ResourceLoader、Tool operations 和 project trust。
- path 输出统一使用绝对 normalized 路径；面向模型的显示路径可以在 cwd 内缩短为 `/` 分隔的相对路径。

上游分别在 `<agentDir>/settings.json` 和 `<cwd>/.pi/settings.json` 加载设置：`D:\pi\packages\coding-agent\src\core\settings-manager.ts:L198-L205 @ e14afc648`。

## 7. Session 目录编码

默认 Session 项目目录兼容上游算法：

1. 解析 cwd 为绝对路径。
2. 移除开头的 `/` 或 `\`。
3. 把 `/`、`\`、`:` 替换为 `-`。
4. 前后加 `--`。

例：`D:\work\repo` -> `--D-work-repo--`。实现必须额外检测编码碰撞；若目录已存在且其中 Header cwd 不匹配，则拒绝并要求 `--session-dir`，不能混写。

源码证据：`D:\pi\packages\coding-agent\src\core\session-manager.ts:L475-L486 @ e14afc648`。

## 8. 文件/Tool 路径语义

- 相对 Tool 路径以当前 runtime cwd 解析；绝对路径保留。
- 为兼容上游，核心默认没有 workspace sandbox，`..` 和 cwd 外绝对路径可以访问；这是显式残余风险，不等于授权模型任意操作。
- mutation 前 canonicalize parent/target，按 canonical path 串行化 write/edit，避免 alias/symlink 并发覆盖。
- edit/write 使用同目录临时文件 + 原子 replace；保留 BOM 与原换行风格，失败不留下部分写。
- read/find/grep/ls 显示路径统一 `/` 分隔，wire 输入不自动改写用户字符串。

上游路径 normalize/resolve 语义：`D:\pi\packages\coding-agent\src\utils\paths.ts:L28-L121 @ e14afc648`。

## 9. Wire 命名

- Python attribute：`tool_call_id`, `stop_reason`, `thinking_level`。
- JSON alias：`toolCallId`, `stopReason`, `thinkingLevel`。
- discriminators 和 enum value 不翻译：`toolResult`、`toolUse`、`follow_up` 等保持原值。
- CLI flag 使用 kebab-case；RPC command type 保持 snake_case；Session entry type 保持 snake_case。
- 不用 Python class name 作为 wire type；codec 显式注册判别值。

## 10. 必测断言

- Windows/Linux home、cwd、UNC/drive-letter、空格、Unicode 和 symlink 路径。
- settings merge 的全组合与未信任项目完全隔离。
- resume/fork/switch 后所有 cwd-bound service 重建。
- `.env` precedence、无祖先搜索、无 shell expansion、secret 不进入 Tool env。
- `.pi` 默认零读取，兼容导入来源 hash 不变。
- Session dir 编码和碰撞拒绝。
- Python snake_case <-> wire camelCase round-trip。
