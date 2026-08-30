# pi-python 当前能力实测报告

- **实测日期**:2026-08-29(第一轮;同日第二轮深入验证见文末 §18)
- **被测版本**:`pi-python 0.5.0`(仓库 commit `45c9726`,分支 `phase/09-pi-tui-claude`,工作区干净)
- **平台**:Windows 10.0.26200 x64,Git Bash 2.50.1.windows.1,`.venv` Python 3.13.9
- **真实模型**:DeepSeek `deepseek-v4-flash`、`deepseek-v4-pro`(`https://api.deepseek.com` OpenAI-compatible streaming)
- **凭据**:已授权读取 `.env` 中的 `DEEPSEEK_API_KEY`;全程仅通过 `--env-file D:\pi-python-claude\.env` 或既有进程环境传递,**未在任何输出、日志、报告中打印密钥**。`auth print-api-key` 只统计了输出形态(35 字符、`sk-` 前缀)后未展示内容,相关临时文件已删除。
- **PTY 方案**:系统 Python 3.13 + `pywinpty`(ConPTY 真伪终端,120×40)驱动真实 `pi-python.exe` 子进程,完成连续多轮 TUI 任务。
- **写入范围**:所有 Agent 产生的文件改动均发生在一次性临时 Git 项目 `%TEMP%\pi-agent-lab`(下文称 lab);本仓库除本报告文件外无任何变化(见文末核对)。

状态标注体系:**验证通过** / **部分可用** / **仅 SDK 可用** / **未接入** / **失败** / **无法验证**。

---

## 0. 结论总览

| 能力 | 状态 | 备注 |
| --- | --- | --- |
| CLI 基线(`--version`/`--help`/`--list-models`/`auth`) | 验证通过 | 与 README §3 完全一致 |
| Headless text(`--print`)Flash/Pro | 验证通过 | 17.5s / 31.0s,质量正常 |
| JSONL 事件流(`--mode json`) | 部分可用 | 每行可独立解析;但 `tool_execution_start/end` 事件**只有 `type` 无负载**,工具结果需从 `message_end`(toolResult)读取 |
| 四个默认工具 read/bash/edit/write | 验证通过 | 均真实执行并回填 ToolResult |
| Bash 成功/失败 | 验证通过 | 成功 exit 0;失败 `isError=true`、`Command exited with code 127` |
| Windows Git Bash 解析 | 验证通过 | 实际解析到 Git Bash(`/usr/bin/bash`);`shellPath` 覆盖未实测(避免改用户级配置) |
| thinking 分级 | 部分可用 | `high` 正常;**`--thinking off` 请求侧正确发送 `thinking: disabled`,但 DeepSeek V4 API 仍返回 `reasoning_content`**;`minimal` 等按文档钳制为 `high` |
| 长流式输出 | 验证通过 | 单轮 2528 个流式事件、21 个编号步骤完整无截断 |
| 错误路径(401/未知模型/缺凭据/未知 provider) | 验证通过 | 均 exit 1、消息干净、不回显敏感值 |
| 自动重试(429/5xx) | 无法验证 | 真实 API 无法确定性触发;产品层 `RetryPolicy` 与 JSON `auto_retry_start/end` 事件存在,由单元测试覆盖 |
| Session 持久化/`--continue`/`--session`/`--session-dir` | 验证通过 | headless 恢复后能回忆上下文 |
| **TUI 交互模式 `--continue`/`--resume`** | **失败(缺陷)** | 不带 `--session-dir` 时抛未捕获 `SessionNotFoundError` 崩溃(见 §8);带 `--session-dir` 可用 |
| regular TUI 多轮真实任务(PTY) | 验证通过 | 诊断→修复→TDD→建文件→长输出→附件 六轮全部完成,产物经磁盘复核 |
| fullscreen TUI | 验证通过 | alt-screen 进出序列齐全,整屏重绘 |
| `/sessions` 切换、`/fork` | 验证通过 | fork 新会话记录 `parentSession`;原会话 hash 证明未被写回 |
| `/attach` 文本附件 | 验证通过 | 以 `[attached file README.md]` 进入下一条 UserMessage |
| `/attach` 图片附件 | 验证通过(按设计拒绝) | `/attach tiny.png` 即时报 `selected model does not support image input` |
| `/copy`(OSC-52) | 验证通过 | 原始 PTY 字节流出现 `\x1b]52` 序列 |
| `/model` 切换 | 验证通过 | TUI 接受 `deepseek/deepseek-v4-pro` 前缀形式 |
| SDK(`create_agent_session`) | 仅 SDK 可用(已实测) | 注入 FakeProvider/内存 SessionManager 跑通完整事件流 |
| `import-pi-session` | 验证通过 | 导入真实 v3 会话,目标文件与源**逐字节一致** |
| `grep/find/ls` 默认注入、trust/包管理命令、`@file`、HTML export、本地 JSONL RPC、远程 Session | 未接入 | 与 README §1 声明一致,实测确认未出现 |
| 压缩/分支摘要 | 仅 SDK 可用 | `compaction_summarizer`/`branch_summarizer` 为 SDK 注入项,默认 CLI 无 summarizer(与 README §6.5 一致) |

---

## 1. CLI 基线(验证通过)

```text
$ pi-python --version
pi-python 0.5.0

$ pi-python --list-models
deepseek/deepseek-v4-flash      DeepSeek V4 Flash
deepseek/deepseek-v4-pro        DeepSeek V4 Pro (default)

$ pi-python --env-file .env auth check
deepseek: ready

$ pi-python --env-file .env auth check --json
{"provider":"deepseek","ready":true}
```

`--help` 输出与 README §3 参数表逐项一致(`--mode text|json`、`--print`、`--tui-mode regular|fullscreen`、`--provider`、`--model`、`--thinking off…max`、`--no-session|--session|--resume|--continue`、`--session-dir`、`--env-file`)。

`auth print-api-key`:exit 0,输出 35 字符、`sk-` 前缀(内容未展示、未留存)。

注意:`--list-models` 展示 `provider/model` 前缀形式,但 **headless `--model` 只接受裸模型 id**:

```text
$ pi-python --print --no-session --model deepseek/deepseek-v4-flash '…'
unknown model for deepseek: deepseek/deepseek-v4-flash      ← exit 1
$ pi-python --print --no-session --model deepseek-v4-flash '…'   ← 正常
```

TUI 的 `/model deepseek/deepseek-v4-pro` 则接受前缀形式(见 §10)。同一目录列表在两处表面上的输入约定不一致,建议在 README §3 注明。

## 2. Headless text(`--print`,Flash/Pro 各一轮,验证通过)

均 `--print --no-session --thinking off`(lab 目录):

| 模型 | 提示词要点 | 耗时 | 结果 |
| --- | --- | --- | --- |
| deepseek-v4-flash | 只读检查架构与测试状态,五点回答 | 17.5s | 正确给出模块结构;**自行运行了 unittest**并指出 `test_receive_increases_stock` 失败(`AssertionError: 7 != 13`)、根因 `receive()` 用减法 |
| deepseek-v4-pro | 三句话说明目录结构与测试命令 | 31.0s | 正确,未调用工具 |

## 3. JSONL 事件流(部分可用)

```bash
pi-python --env-file .env --mode json --no-session --model deepseek-v4-flash \
  '读取 src/stockroom/inventory.py，说明公开函数，不修改文件' > agent-events.jsonl
```

- 440 行,`json.loads` 全部通过,0 行失败。
- 事件类型分布:`message_update`×420、`message_start/end`×4、`entry_appended`×4、`turn_start/end`×2、`agent_start/end`、`tool_execution_start/end`。
- 每行确为独立 JSON,`agent-events.jsonl` 首行为 `{"type":"agent_start"}`,与 README §9.10 预期一致。

**缺陷/局限**:域事件 `ToolExecutionStartEvent/EndEvent` 本含 `tool_name/args/result/is_error`(`src/pi_agent/events.py`),但 `JsonEventPresenter`(`src/pi_coding_agent/presenters.py`)对未匹配类型只输出 `{"type": ...}`:

```text
{"type": "tool_execution_end"}     ← 无 toolName/result/is_error
```

工具负载实际要从 `message_end` 的 `toolResult` 消息读取:

```json
{"type":"message_end","message":{"role":"toolResult","toolCallId":"call_00_…","toolName":"bash",
 "content":[{"type":"text","text":"git version 2.50.1.windows.1\nEXIT_STATUS=0\n"}],
 "details":{"exitCode":0,"truncated":false,"fullOutputPath":null},"isError":false,…}}
```

用量统计出现在 `entry_appended` 记录中(长流式那轮):

```json
"usage":{"input":52,"output":2525,"cacheRead":896,"reasoning":265,"totalTokens":3473,
 "cost":{"total":0.003368424}}
```

## 4. 默认四工具 read/bash/edit/write(验证通过)

单轮 headless 让模型依次 `write` 创建 NOTES.md、`edit` 改 v1→v2、`read` 复核,三个 toolResult 均 `isError=false`,磁盘内容 `lab notes v2` 与汇报一致。JSON 事件流各轮只出现 `read/bash/edit/write`,确认 README "默认只创建四个工具、grep/find/ls 不注入" 的声明。

## 5. Bash 成功/失败与 Git Bash 解析(验证通过)

同一轮执行 `git --version`、`python --version`、故意不存在的命令:

- 成功:`git version 2.50.1.windows.1`、`Python 3.13.9`,`details.exitCode=0`。
- 第一次运行时模型自行给失败命令追加了 `; echo EXIT_STATUS=$?`,把整体退出码洗成 0(`isError=false`,`exitCode=0`)——这是**模型规避行为**,不是工具缺陷;随后用禁止捕获退出码的提示词重测:

```json
{"toolName":"bash","content":[{"type":"text",
 "text":"/usr/bin/bash: line 1: definitely-not-a-real-cmd-xyz: command not found\n\n\nCommand exited with code 127"}],
 "details":{},"isError":true}
```

`isError=true` + `Command exited with code 127` 摘要与 README §6.4/§7.1 的"失败也会成为清理后的可见结果"一致。Bash 实际解析到 Git Bash(`/usr/bin/bash` 行首),Windows 解析链路(`ProgramFiles`/PATH)可用;`settings.json` 的 `shellPath` 覆盖未实测(需写用户级配置,超出本次写入边界),该路径由单元测试覆盖。

## 6. Thinking 分级(部分可用)

- `--thinking off|minimal|low|medium|high|xhigh|max` 全部被 CLI 接受;`minimal` 正常出答(内部钳制为 `high`,与 README 一致)。
- 请求侧(`src/pi_ai/providers/deepseek/request.py`)按文档构造 `extra_body: {"thinking":{"type":"disabled"|"enabled"}}` + 非 off 时 `reasoning_effort`(源码核对无误)。
- **实测偏差**:`deepseek-v4-pro` 以 `--thinking off` 请求两次,均收到真实 `reasoning_content`(如 134 字符英文思考)与 `reasoning` token 计数。即 **off 在当前 DeepSeek V4 API 上不生效**——请求负载正确,API 仍输出思考。使用 off 省 token 的预期目前不成立,README §3 的 thinking 表未提及此 API 行为。
- `--thinking high`:TUI 与 JSON 流均可见 `thinking:` 段/`thinking` content block,展示正常。

## 7. 长流式输出(验证通过)

```bash
pi-python --env-file .env --mode json --no-session --model deepseek-v4-flash --thinking off \
  '用不少于 20 个编号步骤…解释从 CLI、Agent、Provider、工具循环、Session 到 TUI 的完整旅程' > long.jsonl
```

32.1s,2528 个 `message_update` 流式事件,最终文本 4310 字符、21 个编号步骤、收尾完整无截断。regular TUI 中的同题长输出(§9 轮次 5)滚动与 CJK 换行正常,无覆盖残影;宽 ≤ 终端列数(Windows 按 columns-1 防自动换行)在原始字节流中得以验证。

## 8. 错误路径(验证通过)与自动重试(无法验证)

| 场景 | 输出(stderr) | exit |
| --- | --- | --- |
| 无效 key(占位值写入临时 env,未用真实密钥) | `DeepSeek request failed with HTTP 401` | 1 |
| 未知模型 `deepseek-v4-nonexist` | `unknown model for deepseek: deepseek-v4-nonexist` | 1 |
| 缺少凭据(清空环境变量、无 env-file) | `DeepSeek request failed` | 1 |
| 未知 provider `--provider openai` | `unknown built-in provider: openai` | 1 |

所有错误消息均未回显任何密钥值。缺凭据消息比 401 更含糊(未说明"missing credential"),可改进但不算失败。

另确认凭据优先级与 README §3.2 一致:进程环境 `DEEPSEEK_API_KEY` 存在时,`--env-file` 中的假 key **不会**覆盖环境变量(实测)。

自动重试:真实 API 无法确定性制造 429/5xx,本次**无法验证**。产品层 `RetryPolicy`(max 3、2/4/8s 退避)、可重试错误分类、`auto_retry_start/end` JSON 事件、Provider 请求重试与整轮重试互斥(`allows_turn_retry`)均在源码与单元测试中存在;流式过程中本次未遇到可重试错误。

## 9. Session(验证通过;TUI `--continue` 除外)

- 持久化:headless 不带 `--no-session` 时按 `--session-dir ./sess` 生成 v3 JSONL(`…_d1cbb9bf….jsonl`),`entry_appended` 逐条落盘。
- `--continue --session-dir ./sess`:**能回忆上一轮暗号**("菠萝披萨"),且追加写入同一会话文件。
- `--session <path>`:复制会话文件后打开,同样正确回忆暗号。
- 默认目录:`%USERPROFILE%\.pi-python\agent\sessions\--<编码 cwd>--`,与 README §6.5 一致。

**发现缺陷(失败)**:交互 TUI 模式直接 `--continue` 或 `--resume`(不带 `--session-dir`)立即崩溃,未捕获异常:

```text
$ pi-python --tui-mode regular --continue        # 在 ConPTY 中
…
  File "src\pi_coding_agent\tui\runner.py", line 193, in run_interactive
    manager = resolve_session_manager(HeadlessOptions(…))
  File "src\pi_coding_agent\cli\run.py", line 52, in resolve_session_manager
    raise SessionNotFoundError("--session-dir is required with --resume in headless mode")
pi_coding_agent.session.errors.SessionNotFoundError: --session-dir is required with --resume in headless mode
```

原因:交互路径复用 headless 的 `resolve_session_manager`,而后者要求 resume 必须显式 `--session-dir`;交互模式的默认会话目录未被传入。README §3 将 `--resume/--continue` 列为主参数且未注明此限制。**变通**:`--continue --session-dir <默认会话目录>` 后一切正常(§11 即以此方式完成)。

## 10. TUI 命令面(验证通过)

PTY 中逐一验证(regular/fullscreen):

```text
/help      → 8 条命令清单,与 README §4 表完全一致
/model     → current model: deepseek-v4-flash
/model deepseek/deepseek-v4-pro → 接受 provider/model 前缀并切换
/thinking  → current thinking: off
/copy      → 原始 PTY 字节流出现 OSC-52(\x1b]52)序列
/attach tiny.png → "/attach failed: selected model does not support image input"(按设计拒绝,
                    且发生在 attach 期而非请求期)
/exit      → 干净退出(exit 0),无残留进程
```

观察:图片 attach 被拒后,同轮内模型在提示词诱导下**口头声称"收到了图片附件"**(它通过工具在 cwd 找到了 tiny.png 并混淆)。这是 LLM 行为而非附件管线缺陷——管线确实未附加任何图片(请求侧 `_reject_images` + attach 期拒绝双重存在)——但值得在安全边界文档中提示。

## 11. PTY 连续多轮真实任务(regular TUI,验证通过)

ConPTY(120×40)驱动真实 `pi-python.exe --tui-mode regular --model deepseek-v4-flash --thinking off`,在 lab 临时 Git 项目内连续六轮(全程约 8 分钟,逐轮快照存档):

1. **只读诊断**:调用 read/bash,完整运行测试,指出 3 项测试中 delivery 失败、根因 `receive()` 使用减法并给出文件/符号证据;本轮零修改。
2. **最小修复**:先把失败输出存为 `failure-before-fix.txt` 留证,再以 `edit` 把减法改加法,运行完整 unittest 通过;`git diff` 自查仅 `src/stockroom/inventory.py` 一处 hunk。
3. **TDD 新增 transfer**:先加 3 个测试(成功/数量非正/库存不足)确认红灯,再写最小实现并更新 `__init__.py` 导出;6 项测试全绿。
4. **创建 CLI + 全量测试**:`write` 新建 `src/stockroom/cli.py`(argparse/json/sys/pathlib,仅标准库),bash 实测成功路径输出 `{"source": 6, "target": 7}` exit 0、失败路径 stderr 报错 exit 非 0;最后全量测试通过。
5. **长输出**:20+ 编号步骤长中文说明,滚动/换行正常,新输入提示落在新行。
6. **附件**:`/attach README.md` 后提问"只根据附件提取规则、再读源码判断文档是否过时",用户消息中出现 `[attached file README.md]`,模型同时标注"附件声明"与"源码证据"并用 read 复核。

**磁盘复核**(脱离 Agent 独立验证):`git status` 显示恰好 3 个修改文件 + `cli.py` 新增;`git diff` 中 `receive` 为 `- return stock - quantity` → `+ return stock + quantity`;`python -m unittest discover -s tests` → `Ran 6 tests … OK`;手动运行生成 CLI:`{"source": 6, "target": 7}` exit 0,`--quantity 0` → `error: quantity must be positive` exit 1。

## 12. 退出重启、/sessions 切换、/fork(验证通过)

第二轮 PTY:

1. 以 `--continue --session-dir <默认会话目录>` 重启(直接 `--continue` 崩溃,见 §8)。
2. `/sessions` 列出 `1. ded58eed… (current)` 并以编号 `1` 选择切换。
3. 提问"总结已完成任务,并读取当前源码验证,不要只依赖历史回答":模型重新 read 源码,引用 `inventory.py:13-18` 确认 `transfer` 实现存在——上下文恢复 + 工具复核均有效。
4. `/fork` → 输出 `forked to 37ab74e8d08e44c3899e8a8138585253`;新会话文件头部记录 `"parentSession": "<原会话绝对路径>"`。
5. 在 fork 中讨论"transfer 改为返回 dataclass 的迁移方案"(纯讨论,未改文件),模型给出分阶段迁移建议。

**写回隔离证明**(sha256 前 16 位):

| 时刻 | 原会话 ded58eed | fork 会话 37ab74e8 |
| --- | --- | --- |
| fork 提问回答后 | `4237f62713690aae` | — |
| `/fork` 后 | `4237f62713690aae`(未变) | `5c5fd4b6dd282e6a`(新建) |
| fork 内 dataclass 讨论后 | `4237f62713690aae`(仍未变) | `47b92f6d04ab62dd`(增长) |

即 fork 之后的所有讨论只写入新会话,原会话字节级不变——与 README §6.5 "fork 原子复制所选活动路径,并记录父 Session"一致。

## 13. fullscreen TUI(验证通过)

`--tui-mode fullscreen --no-session`:

- 进入时输出 `\x1b[?1049h`(alt-screen),`/exit` 后输出 `\x1b[?1049l` 恢复原终端;
- `/help`、`/model`、`/thinking`、`/attach` 全部可用(输出见 §10);
- 真实问答一轮,整屏重绘、CJK 换行正常,退出无残留。

## 14. SDK 与导入器(实测通过)

**异步 SDK**(`pi_coding_agent.sdk`,离线 FakeProvider):

```python
runtime = ModelRuntime(provider=FakeProvider([fake_assistant_message((TextContent(text="sdk-ok"),))]),
                       model=provider.models[0])
created = await create_agent_session(CreateAgentSessionOptions(
    cwd=…, model_runtime=runtime, session_manager=SessionManager.in_memory(…)))
await created.session.prompt("ping")   # 返回 None;从 session.messages 读最终 AssistantMessage
# SDK reply: sdk-ok
# 事件流: agent_start/end, turn_start/end, message_start/update/end, entry_appended
```

注意两点:① `CreateAgentSessionOptions` 没有 `provider`/`no_session` 字段,Provider 要经 `model_runtime` 注入、无会话要传内存 `SessionManager`(README §7.2 示例省略了这些参数,照抄会 `TypeError`);② `session.prompt()` 返回 `None`,README §7.2 示例只 `await` 未取返回值,与实现一致但易被误读。

`sync_sdk` 模块存在(同步包装类齐全),本次未深测。`compaction_summarizer`/`branch_summarizer` 仅作为 SDK 注入项存在,默认 CLI 无 summarizer——确认 README "已实现但不默认启用" 的分层描述。

**`import-pi-session`**:把本次真实 TUI 会话(110 KB v3 JSONL)导入到新目录,exit 0,目标文件与源文件 `cmp` **逐字节一致**——验证了"先严格验证、再复制原始字节"的契约。

## 15. README 逐节审计

| README 章节/声明 | 实测结论 |
| --- | --- |
| §1 能力三层表:默认 CLI/TUI 支持 DeepSeek 对话、流式 thinking/text、四工具、v3 Session、regular/fullscreen、文本附件、切换与分叉 | **验证通过**(TUI `--continue` 缺陷除外,见 §8) |
| §1 "grep/find/ls 未默认注入;仅 SDK 可注入" | **验证通过**(各轮 JSON 流只见 read/bash/edit/write;SDK `tools=` 注入口存在) |
| §1 尚未接入:trust 命令、包安装命令、`@file`、HTML export、本地 JSONL RPC、远程 Session | **未接入**,与实测一致(命令不存在、无相关 surface) |
| §2 快速开始(`uv run --frozen pi-python`)、§2.2 操作另一项目(cwd 即工作目录) | **验证通过**(lab 全程以该方式运行) |
| §2.3 Windows Bash 选择、`shellPath` | **部分可用**:解析链路实测可用;`shellPath` 覆盖未实测(避免写用户级配置),由单元测试覆盖 |
| §3 参数表 | **验证通过**,两处补充:`--model` 不接受 `provider/` 前缀(§1);interactive `--resume/--continue` 需显式 `--session-dir` 否则崩溃(§8),README 未注明 |
| §3.1 JSON 模式"输出 Agent、消息、工具和流式状态事件" | **部分可用**:类型齐全,但工具事件无负载(§3),建议文档注明 |
| §3.2 凭据优先级、`auth`、`import-pi-session` | **验证通过** |
| §4 TUI 命令表(8 条)、文本附件 UTF-8 全文嵌入、regular/fullscreen 渲染说明 | **验证通过**(含 CJK 宽度、Windows 减一列防自动换行) |
| §5 包边界、入口文件 | **验证通过**(import 实测:SDK 冒烟按边界导入成功) |
| §6 执行流程、§6.4 工具循环(校验/串行化/失败可见)、§6.5 Session(v3、严格读取、fork 记录父会话) | **验证通过**(§9/§11/§12;"首个 Assistant 出现前延迟建文件"未单独实测) |
| §6.3 "Provider 默认不做底层自动重试;产品层最多三次、2/4/8s;两层独立可观察" | **无法验证**(真实 API 未触发);源码与单测支持该描述 |
| §7.1 工具行为表(截断阈值、超时、原子写等) | **部分验证**:常规读写、错误摘要、`details.exitCode/truncated/fullOutputPath` 字段实测;截断/超时/取消路径未逐一实测(需构造大输出/挂起进程) |
| §7.2 可注入工具与 SDK | **仅 SDK 可用,已实测**(§14;README 示例参数不完整需修正) |
| §7.3 Extension/prompts/themes/包底层/telemetry | 未深测(超出本轮范围);FakeProvider 已在 SDK 冒烟中间接验证 |
| §8 安全边界(不限制 cwd、PermissionGate 默认关、附件无大小上限提示) | **验证通过**(工具曾按绝对路径在 cwd 外读写;未发现任何确认弹窗) |
| §9 真实完整对话测试脚本 | **验证通过**:§9.1-§9.10 全部按脚本走通(§11-§13),包括"失败不被伪装成功"的 Bash 用例 |
| §12 已知未完成项 | 与实测一致 |

**README 遗漏/需修正项汇总**:

1. TUI `--resume/--continue` 不带 `--session-dir` 会崩溃(缺陷,建议修复后文档无需特例);
2. headless `--model` 与 `/list-models`、TUI `/model` 的模型 id 形式不一致;
3. `--thinking off` 在当前 DeepSeek V4 API 上仍产生 reasoning 输出(API 行为);
4. JSON 模式工具事件无负载,工具结果需读 `message_end`;
5. SDK 示例缺少 `model_runtime`/`session_manager` 注入细节,`prompt()` 返回 `None` 未说明。

## 16. 耗时与成本摘要

| 项目 | 模型 | 耗时 | 备注 |
| --- | --- | --- | --- |
| Headless 五点架构回答 | flash | 17.5s | 含自行跑测试的 bash 轮 |
| Headless 三句话回答 | pro | 31.0s | 纯文本轮 |
| JSONL 单轮(read 工具) | flash | 9.2s | 440 事件 |
| thinking off/high 对照 | pro | ≈10–15s/轮 | off 仍含 reasoning(§6) |
| 长流式(21 步) | flash | 32.1s | 3,473 tokens,成本 $0.00337(usage 记录) |
| TUI 六轮任务 | flash | ≈8.5 min | 含多次工具调用与测试执行 |
| 恢复/切换/fork 轮 | flash | ≈7 min | 含重启与两轮问答 |
| fullscreen 轮 + /copy 轮 | flash | ≈2 min | 命令面验证 |

## 17. 仓库变更核对与遗留物

- 本仓库:**仅新增本文件** `docs/current-agent-validation.md`;`git status` 无其他变化(验证期间由会话工具生成的 `.zcode/plans/` 计划草稿已删除)。
- 临时产物(均在 `%TEMP%`,可整目录删除):`pi-agent-lab/`(实验项目 + Agent 会话与事件样本)、`imported-sessions/`、`tui_driver*.py`(ConPTY 驱动)、各轮 transcript 快照。
- 运行时数据(非仓库):`%USERPROFILE%\.pi-python\agent\sessions\` 下为 lab 项目生成的两个真实会话文件(原会话与 fork),以及 headless `sess/` 会话(在 lab 内)。
- 密钥安全:真实密钥从未进入任何输出或报告;测试期间短暂生成的 `key.txt`(print-api-key 输出)与 `fake.env`(占位值)已删除。

---

## 18. 第二轮深入验证(同日续):代码深挖、one-shot、取消行为、截断边界、上游对比

第二轮针对第一轮未覆盖的内部行为与产品差距,结论先行:

| 新验证项 | 状态 | 要点 |
| --- | --- | --- |
| 单提示词 one-shot 完整任务 | **验证通过** | 一段提示词自主完成"建工具→TDD→CLI→README→git 提交"全流程(§18.1) |
| 流式中取消(Esc/Ctrl+C) | **失败(差距)** | ConPTY 实测两者都无法中断运行中的回合,也无任何取消 UI;回合只能等其自然结束(§18.2) |
| 输入历史召回(↑) | 验证通过 | prompt_toolkit 内存历史;重启即失,无持久化 |
| 重启后历史重放 | 未实现(代码确认) | 恢复的 session 只进模型上下文,TUI 界面从空白开始(§18.3) |
| bash 输出截断 | 验证通过 | 保留尾部 2000 行/50KB,`truncated:true` + `fullOutputPath` 临时完整日志(§18.4) |
| read 截断 | 验证通过 | 2000 行上限,`nextOffset` 续读提示(§18.4) |
| steering / follow-up | 仅 SDK 可用 | `Agent.steer()/follow_up()` 实现完整且单测通过,但产品 CLI/TUI 从不调用——回合内无法追加消息(§18.5) |
| 上下文管理 | 部分可用 | 无 token 计数、无阈值自动压缩;全量历史每轮重发;溢出时仅在 SDK 注入 summarizer 后有一次性恢复(§18.6) |
| 与上游 D:\pi 对比 | 见 §18.7 | 缺 RPC/HTML export/@file/@-补全/图片粘贴/15+ slash 命令/鼠标;thinking 级别映射与上游不同 |

### 18.1 单提示词 one-shot 完整任务(验证通过)

全新临时 Git 目录,一条中文提示词(任务书:纯标准库 `wordfreq` 词频工具,含 core/CLI/unittest≥3 例/先红后绿/样例运行/README/git 提交,并明确"不要向我提问"):

```bash
pi-python --print --model deepseek-v4-flash --session-dir ./sess "$(cat TASK.md)"
```

结果:一次交互内自主完成,无需任何人工干预——

- `src/wordfreq/core.py`、`src/wordfreq/cli.py`、`tests/test_core.py`(实际写了 6 个用例)、`README.md`、`sample.txt`、`.gitignore`;
- `python -m unittest discover -s tests` → `Ran 6 tests … OK`;
- CLI 实测:`python -m wordfreq.cli sample.txt --top 3` → `the 8 / quick 7 / brown 6`,exit 0;
- `git log` → `d8bb859 add wordfreq tool`。

这证明当前 Agent 已具备 codex 式"一段话交付一个完整任务"的多轮自主能力(规划→TDD→自测→自检→落盘)。

### 18.2 流式中取消行为(失败,与上游差距)

ConPTY 实测(regular TUI,长输出任务运行中):

- `Esc`:无任何效果,流式继续(代码核对:`app.interrupt` 动作在 `pi_tui/actions.py` 声明但产品零消费;`AgentSession.abort()` 在 TUI 路径中从未被调用);
- `Ctrl+C`(回合运行中):**同样无效果**,20 秒后进程仍存活且继续输出;ConPTY 将其作为普通输入字节投递,运行中的 `handle()` 不读取 stdin;
- `Ctrl+C`(等待输入时):立即退出整个 TUI(prompt_toolkit 取消 prompt → KeyboardInterrupt → exit 130),无"已中止"的界面反馈。

即:当前 TUI **没有任何在 UI 内取消正在运行回合的手段**;唯一退出方式是等回合结束再 `/exit`(或 Ctrl+C 杀掉整个进程)。上游 pi 有 Esc 中断 + `AgentSession.abort()` 后端支持(后者 pi-python SDK 已实现,仅缺产品接线)。

### 18.3 重启后的历史重放(未实现)

- 实测:第二轮 PTY 以 `--continue --session-dir …` 重启后,界面为空白提示符,看不到此前 6 轮对话(与我第一轮截图观察一致);
- 代码确认:`rebuild()` 传 `initial_lines=()`;恢复消息只进入 `Agent` 构造参数(模型上下文),`InteractiveApp` 仅渲染订阅到的新事件;存在专门测试 `test_each_completed_turn_is_rendered_once_without_replaying_history` 锁定该行为。
- 影响:恢复会话后用户看不到"我们刚才做了什么",只能靠提问回忆;`/sessions` 切换同理(仅提示 `switched to …`)。

### 18.4 截断边界(验证通过)

- **bash**:强制 `cat big.txt`(3000 行)→ `details.truncated=true`、`fullOutputPath=C:\Users\…\Temp\pi-bash-*.log`,返回文本保留**尾部** 1001–3000 行并追加 `[Showing lines 1001-3000 of 3000. Full output: <path>]`,与 README §7.1"尾部截断 2000 行/50KB + 完整输出写临时日志"一致;
- **read**:3000 行文件 → 返回 1–2000 行,`details.nextOffset=2001`,追加 `[Showing lines 1-2000 of 3000. Use offset=2001 to continue.]`。

### 18.5 steering / follow-up 队列(仅 SDK 可用)

`pi_agent` 实现完整:回合中 `agent.steer(msg)` 在下一轮前注入(优先于 follow-up),`follow_up(msg)` 在无工具链时开新轮;`prompt()` 运行中再次调用会明确报错引导用 steer。仓库单测 `tests/pi_agent/test_agent_queues.py` 3 项通过。但 `src/pi_coding_agent` 中无任何调用——**产品 CLI/TUI 用户无法在回合进行中追加消息**,只能排队等待回合结束。这是与 codex/pi 上游"随时插话"体验的另一差距(上游交互模式支持输入排队)。

### 18.6 上下文管理与压缩(部分可用)

- 默认循环**无 token 计数、无阈值自动压缩**;全量历史每轮重发给模型;
- 压缩仅两条路:SDK 显式 `session.compact()`;或 provider 报上下文溢出错误时的一次性恢复(且必须注入了 `compaction_summarizer`,默认 CLI 没有)→ 默认产品实际**无任何压缩**;
- `stop_reason=="length"` 时未执行的 tool call 会被统一置为错误结果,行为正确。

### 18.7 与上游 D:\pi(e14afc648, Pi 0.84.1)的对比

一致(核心):7 个工具及默认四工具、v3 session 格式/存储路径、事件模型、JSONL RPC 之外的 CLI 主干 flags、DeepSeek thinking wire 格式(`thinking:{type}` + `reasoning_effort`)。

pi-python 当前缺口(除计划内 Post-v1 外,对"达到 codex/pi-agent 体验"影响较大的排前):

1. **回合内取消**(§18.2)与**回合中插话**(§18.5)——交互体验最大差距;
2. **重启/切换后不重放历史**(§18.3);
3. slash 命令仅 7 个,上游 22 个(缺 `/settings /export /import /tree /trust /new /name /compact /login …`);
4. 无 `@file` 位置参数、无 `@`-mention 文件补全、无图片粘贴(上游 autocomplete.ts/interactive-mode.ts 均有);
5. TUI 无鼠标支持、无持久输入历史、无 slash 补全、宽度不随 resize 更新;pi_tui 库中 Editor/Keybindings/Autocomplete/Dialogs 已实现但产品未接线(产品用裸 prompt_toolkit 单行 PromptSession);
6. ~~thinking 级别映射分歧~~ **更正(第三轮)**:复读上游 `getSupportedThinkingLevels` 后确认,上游 `thinkingLevelMap` 将 minimal/low/medium 映射为 `null` 的效果是**把它们从支持级别中剔除**,经 `clampThinkingLevel` 后仍为 `high`(`xhigh→max`)——与 pi-python 现行为**完全一致**,此项并非分歧;已加锁定测试 `test_deepseek_thinking_clamp_matches_upstream_thinkinglevelmap`(`ca83422`)防止回归;
7. RPC 模式(`--mode rpc`)与 HTML export 未实现(矩阵标 Supported/Phase 12,代码未落地)。

另有产品未使用 pi_tui 通用层导致的重复实现:`InteractiveApp` 自建块渲染,而 `pi_tui.Application/ScreenRenderer` 只被 fullscreen 路径部分复用。

### 18.8 对话历史存档

本轮新增 `docs/agent-dialogue-history.md`:由真实 v3 Session JSONL 自动导出的 4 个会话、18 轮完整对话(用户消息、助手 thinking 摘要、全部 toolCall 参数与 toolResult、最终文本),覆盖 TUI 六轮任务、fork 分支、headless 记忆测试与 one-shot 任务,供人工核对渲染内容与工具轨迹。

---

## 19. 第三轮:缺陷修复与真实复测(2026-08-29)

针对前两轮发现的缺陷,按"失败测试 → 最小实现 → 测试通过 → 真实 API/PTY 复测"的循环逐项修复。全部通过完整回归门:`pyright` 0 错误、`ruff check/format` 干净、`pytest -m "not live_provider and not network"` **632 通过**、`uv build --no-sources` 成功。

### 19.1 修复清单(提交)

| # | 缺陷(前两轮编号) | 修复提交 | 单元测试 |
| --- | --- | --- | --- |
| F1 | TUI `--continue`/`--resume` 不带 `--session-dir` 崩溃(§8) | `18ba4a6` 交互路径回退到 `default_session_dir(cwd)` | `test_interactive_resume_without_session_dir_continues_newest_session` |
| F2 | JSON 模式工具事件无负载(§3) | `0e3b6f1` presenter 输出 `toolCallId/toolName/args/partialResult/result/isError` | `test_json_presenter_includes_tool_execution_payloads` |
| F3 | headless `--model` 拒绝 `provider/model` 前缀(§1) | `b28a24e` `create_model_runtime` 规范化前缀,未知 provider 前缀仍报错 | 3 项 `test_create_model_runtime_*` |
| F4 | 报告误判"thinking 映射分歧"(§18.7) | `ca83422` 复核上游后确认行为一致,加锁定测试;报告已更正 | `test_deepseek_thinking_clamp_matches_upstream_thinkinglevelmap` |
| F5 | 缺凭据时报含糊的 "DeepSeek request failed"(§8) | `9b420e5` provider 抛 `MissingCredentialError` 并透传可操作消息 | `test_missing_credential_yields_actionable_error_message` |
| F6 | 重启/切换后 TUI 不重放历史(§18.3) | `7421b67` `render_replay_lines()` 将恢复消息渲染进 transcript(启动/resume/`/sessions`/`/fork` 生效) | `test_replay_renders_restored_history_on_interactive_resume` |
| F7 | 回合中 Esc/Ctrl+C 无法取消、无法插话(§18.2/§18.5) | `1a2856f` 回合期间非阻塞轮询控制台按键:Esc/`Ctrl+C`→`session.abort()`+`cancelled` 状态行;输入一行+回车→`agent.steer()`+`steered:` 状态行;管道输入自动降级 | `test_escape_during_a_turn_aborts_and_reports_cancellation`、`test_input_typed_during_a_turn_is_queued_as_steering` |
| F8 | README 与实际行为脱节(§18.7) | `5bcd7de` 参数表/JSON 模式/凭据/TUI 键盘与重放全部同步 | — |

实现过程中发现并修掉一个自引入缺陷:按键轮询在持续有输入时同步死循环饿死事件循环(debug 复现)→ 消费按键后强制 `await asyncio.sleep(0)`,abort 后立即停止轮询。

### 19.2 真实 API / 真实 ConPTY 复测证据

1. **F3**:`--model deepseek/deepseek-v4-flash --print` → 正常回答,3.98s。
2. **F2**:`--mode json` 真实 bash 轮,逐行解析出完整负载:
   `{"type":"tool_execution_start","toolCallId":"call_00_YVZq…","toolName":"bash","args":{"command":"git --version"}}` → `update`/`end` 均含 `partialResult`/`result`(`content` + `details.exitCode:0`)与 `isError`。
3. **F1+F6**:真实 PTY 直接 `--continue`(无 `--session-dir`)→ 进程存活、历史重放进入 transcript、随后提问"我们修的是什么 bug" → 模型回答正确引用 `receive` 函数(上下文延续),`/exit` 干净退出。
4. **F7a 取消**:真实 PTY 长流式回答进行 15s 后按 `Esc` → 输出停止增长(delta 397 字节)、屏幕出现 `cancelled`、提示符恢复、`/exit` 正常退出。
5. **F7b 插话**:真实 PTY 要求"30 段×60 字描写海洋",流式中输入"改成三句话总结就好"+回车 → 出现 `steered:` 确认行,模型最终输出为三句话总结(steering 被下一轮消费)。
6. **F5**:清空 `DEEPSEEK_API_KEY` 且无 `--env-file` → stderr 精确输出 `No credential configured for deepseek; set DEEPSEEK_API_KEY or provide an explicit API key`,exit 1。
7. **thinking off**:请求侧行为正确(`thinking: disabled`),API 仍返回 reasoning 属上游 API 行为,README §3 已注明;无代码可修。

### 19.3 仍属路线图、未在本轮处理的项(非缺陷)

`--mode rpc`、HTML export、`@file` 参数、`@`-mention 补全、图片粘贴、15+ 上游 slash 命令、鼠标支持、默认自动压缩——均为 surface matrix 中 Phase 12 / Post-v1 规划项,维持"未接入"状态,详见 §18.7。

### 19.4 仓库状态

代码分支 `phase/09-pi-tui-claude`,本轮新增提交:`18ba4a6`、`0e3b6f1`、`b28a24e`、`ca83422`、`9b420e5`、`7421b67`、`1a2856f`、`5bcd7de`、`632414f`(类型清理)。工作区仅 `docs/current-agent-validation.md` 与 `docs/agent-dialogue-history.md` 两个未跟踪文档;源码、测试、配置均以提交形式落在分支上,无其他未提交改动。

### 19.5 第四轮:真实用户环境 TUI 反馈修复(2026-08-29)

用户在 PowerShell + `uv tool install` 的真实环境实测后反馈四个问题,全部修复(`a113351`):

| 用户反馈 | 根因 | 修复 | 真实 PTY 复测 |
| --- | --- | --- | --- |
| `--continue` 报裸 traceback | 该目录尚无已持久化会话(上次回合被 Ctrl+C 打断,首个 assistant 未完成,延迟建文件未触发),`SessionNotFoundError` 未在交互路径捕获 | 交互 resume 失败时打印提示并**自动开始新会话** | 新目录 `--continue`:提示 `no sessions found… starting a new session`,无 traceback,可正常对话 |
| 空闲时 Ctrl+C 直接退出会话 | 主循环读行处捕到 KeyboardInterrupt 立即返回 130 | **两次** Ctrl+C(2 秒内)才退出;第一次清行并提示 `press Ctrl+C again to exit` | 单击:提示出现、进程存活;双击:退出 |
| 回合中 Ctrl+C 崩溃 + `asyncgen … GeneratorExit` 噪音 | Windows 控制台默认 `ENABLE_PROCESSED_INPUT`,Ctrl+C 走 SIGINT 绕过按键轮询,进程硬中断留下未关闭的 httpcore 流 | 回合期间临时清除该标志(POSIX 清 `ISIG`),`\x03` 作为普通键进入轮询 → 优雅 abort;回合结束恢复控制台模式 | 回合中 Ctrl+C:输出停止、`cancelled` 显示、**无 Traceback/asyncgen 噪音**、进程存活 |
| `/model deepseek` 失败且不友好;按 `/` 无提示;无法自由切换 | 无模型匹配辅助、无补全器 | `match_model_argument`:精确/裸 id/**唯一部分匹配**(`flash`),歧义或未知时**列出可用模型**;`/thinking` 非法值列出全部合法级别;新增 `SlashCompleter`(prompt_toolkit Completer)——`/` 弹出命令菜单,`/model`、`/thinking` 参数子串补全 | `/model flash` → `model: deepseek/deepseek-v4-flash`;`/model deepseek` → 列出两个候选;`/thinking xyz` → 列出 7 个合法级别;`/` 原始字节中出现完整灰色下拉菜单(含命令与描述) |

新增/更新测试 5 项(resume 降级、模型匹配、补全器、双击退出、单击提示),TUI+smoke 75 项全绿;回归门再次全绿(pyright 0、ruff 干净、全量 637 通过、`uv build` 重新生成 dist wheel)。README §3/§4 已同步。

用户侧更新方式:`uv tool install --force D:\pi-python-claude`(dist wheel 已重新构建)。

---

## 20. 差距分析:vs Codex/Claude Code、vs 上游 Pi 工具、Session 正确性、计划余量(2026-08-30)

> 本节为合并 `phase/09-pi-tui-claude` → `main`(merge commit `cc00d71`,已推送 GitHub)时的快照分析;工具/Session 结论基于对 `D:\pi`(e14afc648)与本项目源码的逐文件对照。

### 20.1 与 Codex CLI / Claude Code 的差距(产品级)

| 维度 | Codex / Claude Code 已有 | pi-python 现状 |
| --- | --- | --- |
| 权限与沙箱 | Codex:OS 级沙箱(macOS seatbelt/Linux landlock)+ 审批模式;CC:权限提示/允许清单/hooks | 仅有未接线的 `PermissionGate` 脚手架,默认关闭,bash 无任何隔离 |
| 上下文管理 | 两者都有自动压缩/摘要 | 无 token 计数、无自动压缩;仅 SDK 手动 + overflow 一次性恢复 |
| 任务规划 UI | Codex update_plan;CC TodoWrite/Plan mode | 无 |
| 生态集成 | 两者都是 MCP client;CC 有 subagent/后台任务/skills/hooks/web | 无 MCP、无 subagent、无 web 工具;Extension 注册表存在但 CLI 未接线 |
| 多模态 | 图片输入(读图/粘贴) | 模型目录 text-only,read 工具不支持图片 |
| 补全/交互 | 成熟的命令面板/文件 @-补全 | 本轮已加 `/` 命令与参数补全;仍无 @file 补全、无鼠标 |
| Session | 两者:resume/continue;CC 另有 fork(JSONL transcripts) | v3 JSONL + 树/fork/recovery(部分强于上游,见 20.3) |

### 20.2 工具层 vs 上游 Pi(7 工具逐项对照)

共享语义已忠实复刻:2000 行/50KB 截断、续读 offset、尾部截断+完整输出 spill 文件、BOM/CRLF 感知 edit、唯一性/重叠校验、per-realpath 串行化、超时/abort/退出码文案。pi-python 额外多出:原子写+fsync、PermissionGate、PowerShell 扩展。

**缺失/未接线(按影响排序)**:
1. **grep/find/ls 无生产实现**——`operations.py` 只定义 Protocol,`binaries.py` 的 pinned ripgrep/fd 下载器从未接线,SDK 硬编码 `create_coding_tools`,三工具完全不可达(上游默认全 7 工具可用)。
2. **read 不支持图片**(上游 jpg/png/gif/webp/bmp + 2000×2000 缩放);无 macOS 路径变体回退。
3. **edit 无 diff/patch 输出**(上游 details.diff/patch/firstChangedLine 支撑 UI diff 预览)、**无模糊匹配回退**(NFKC/智能标点/尾随空白)。
4. **bash 无 PI_* 会话环境注入、无 commandPrefix/spawnHook/binDir PATH、更新不带 details、无限流节流**。
5. grep 缺 glob/ignoreCase/literal/context 参数与 `--json` 流式;find 缺 fd 细节(`--full-path` 等);二者输出格式偏差(`:column:`)。
6. 无 readonly 工具集助手、无 allowlist/denylist/defaultTools 设置、CLI 无工具开关与 `--approve/--no-approve` 信任标志。
7. 工具描述不贡献 promptSnippet/截断限制说明;无 constrainedSampling。

### 20.3 Session 管理正确性判定

**结论:在文档化范围内(v3 JSONL、本地单用户)是正确的,且多处比上游更稳。** 已验证:延迟建文件、逐条 fsync+0600(上游不 fsync)、单根前向树、与上游语义一致的压缩投影、目录损坏文件隔离为诊断项、逐字节导入、原子 fork、上游没有的 unmatched-tool-call recovery。

风险/缺陷清单:
- **[RISK] 崩溃撕裂行严格拒读**(`reader.py:26-34` vs 上游跳过坏行 `session-manager.ts:299-313`):写一半崩溃会让整个会话无法打开(仅隔离+提示),上游只丢最后一条。文档声明为有意分歧,但**无修复 CLI**——建议后续加"截断末行修复"命令。
- **[RISK] 未知记录类型导致整文件不可读**(上游透传)——前向兼容弱。
- **[BUG] `--name`/SessionInfoEntry 无任何写入方**,但 surface matrix `CLI-FLAG-020` 标为 Supported——矩阵与代码不符。
- [RISK] catalog cwd 过滤比上游严(Windows 盘符大小写/目录改名会藏会话);[RISK] 大会话全量载入+双重校验+O(n·depth) 验证,上游流式+4KB 头扫描;[RISK] `open_session` 不支持"打开即创建"(上游支持);[RISK] UNC/相对 cwd 的目录编码与上游不一致(当前调用方均传绝对路径,未触发)。

### 20.4 计划余量

- 14 个阶段:P0–P11 完成(Phase 11 修复仍以 Unreleased 进入本分支);**P12(9 项)与 P13(7 项)未开始**,todo 总量 147,未勾选 16。
- Surface matrix 231 项:Supported 190(**约 63 项未落实**,集中于 RPC 19、CLI 标志 30、子命令 6、SDK 导出 3、设置接线 3、发布冒烟 2)、有意分歧 28、Post-v1 13(明确不做)。
- ADR 已钉死边界:1.0 不做 Harness/SQLite/lanes/CBOR 远程、DeepSeek-only、无 JS 扩展、严格 v3。

### 20.5 建议的下一步优先级

1. **P12-T01 CLI 大合并**(一次性补 30 个标志 + 工具 allow/deny + trust/approve)——消除最大的矩阵缺口;
2. **grep/find 生产接线**(BinaryManager → SearchOperations,半天工作量,直接从"4 工具"变"7 工具");
3. **read 图片 + edit diff/模糊匹配**(对齐上游体验);
4. **自动压缩**(threshold watcher + /compact 命令)——向 Codex/CC 的上下文管理看齐;
5. **撕裂行修复命令 + `--name`**(补 session 两个短板);
6. 之后按计划走 P12 RPC → P13 发布门。
