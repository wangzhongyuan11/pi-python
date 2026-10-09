# pi-python 使用指南

本文描述当前源码的真实行为。命令与 `pi-python --help` 保持一致;当文字与实际命令冲突时,
以 `--help` 与源码为准。

## 1. 启动与模型

```bash
# 交互式 TUI(默认)
pi-python

# 全屏 TUI
pi-python --tui-mode fullscreen

# 无头单轮(text 模式)
pi-python -p "总结这个项目的结构"

# JSON 事件流(供程序消费)
pi-python --mode json -p "列出所有 todo"

# 指定模型与思考级别
pi-python --provider deepseek --model deepseek-v4-flash --thinking high
pi-python --list-models
```

模型能力与目录由 DeepSeek 受审目录提供;`--thinking` 取值
`off|minimal|low|medium|high|xhigh|max`,按模型能力自动收敛。

## 2. 会话选择与命名

```bash
pi-python --continue            # 继续当前 cwd 最近一次会话
pi-python --resume              # 交互选择历史会话
pi-python --session <path|id>   # 打开指定会话(路径或部分 id)
pi-python --session-id <id>     # 存在则打开,不存在则创建
pi-python --fork <path|id>      # 复制完整历史到新会话
pi-python --name "重构任务"      # 会话显示名(写入 session_info entry)
pi-python --session-dir <dir>   # 自定义会话目录
pi-python --no-session          # 本次运行不持久化
```

## 3. 文件附件(@file)

位置参数里以 `@` 开头的词会被展开为附件:文本文件进 `<file>` 信封,图片(按扩展名
识别 png/jpg/jpeg/webp)转成 ImageContent 附件,要求当前模型支持视觉输入。

```bash
pi-python -p "解释这份配置" @config.yaml @architecture.png
```

- 缺失文件:`File not found: <绝对路径>`(退出码 1)
- 空文件:静默跳过
- 文本模型 + 图片附件:`selected model does not support image input`
- RPC 模式(`--mode rpc`)拒绝 `@file` 参数
- TUI 内使用 `/attach <path>` 达到同样效果

## 4. 工具选择

```bash
pi-python --tools all                 # 全部七个内建工具(read/bash/edit/write/grep/find/ls)
pi-python --tools read,grep           # 只启用指定内建工具
pi-python --exclude-tools bash        # 全集中排除指定工具
pi-python --no-builtin-tools          # 关闭全部内建工具(保留扩展工具)
pi-python --no-tools                  # 全部禁用
```

## 5. 扩展与资源

```bash
pi-python --no-extensions            # 不加载任何扩展
pi-python --skill <name>             # 只加载指定 skill
pi-python --no-skills
pi-python --prompt-template <name>
pi-python --theme <name>             # 主题按名叠加
pi-python --no-context-files         # 不读 AGENTS.md 等上下文文件
```

Python 扩展(`pi-extension.json` + `main.py`)与上游 TypeScript 扩展
(`*.ts`,经 Node host)都可执行;TypeScript 扩展无法跨进程呈现的能力
(自定义 TUI 组件、自定义 Provider)会在安装检查中报告为 unsupported。

## 6. 包管理

```bash
pi-python install <source> [--no-approve]
pi-python list
pi-python config <name> enabled|disabled
pi-python update [<source>|self|pi] [--offline]
pi-python remove <source>
pi-python uninstall <source>    # remove 的别名
```

`<source>` 支持本地目录、Git URL、PyPI 包名与 npm 包名。npm 包只提取数据资源,
永不执行其脚本;TS 扩展经 Node host 激活。

## 7. 认证

```bash
pi-python auth check [--json] [--no-refresh]
pi-python auth print-api-key       # 仅显式调用时把 key 写 stdout
```

凭据优先级:CLI `--api-key` > 环境变量 `DEEPSEEK_API_KEY` > `.env` 文件。

## 8. 会话维护与导入

```bash
pi-python session repair <file>            # 截断损坏的最后一行
pi-python import-pi-session <source>       # 上游 .pi → 新 .pi-python 会话
pi-python --export <out.html> --session <path|id>   # HTML 导出
```

HTML 导出是转义优先的:模型输出、工具结果与扩展消息中的 HTML/ANSI 都不会在
导出文档中执行。

## 9. RPC 模式

```bash
pi-python --mode rpc
```

stdin/stdout 上按行交换 JSON:请求 `{"type":"get_state"}`、`{"type":"prompt","message":...}`、
`{"type":"compact"}`、`{"type":"export_html","outputPath":...}` 等;事件以
`agent_start`/`message_update`/`agent_end` 等流回。RPC 模式不接受位置参数或 `-p`,
也不支持 `@file` 参数。Python 侧可用 `pi_coding_agent.rpc.client.RpcClient` 驱动。

## 10. 退出码

| 退出码 | 含义 |
| --- | --- |
| 0 | 成功 |
| 1 | 运行期错误(凭据缺失、会话损坏、附件错误等) |
| 2 | 用法错误(未知参数、互斥标志冲突) |
| 130 | Ctrl+C 中断 |
