# ADR 0005：受控 DeepSeek V4 模型目录

- 状态：Accepted
- 日期：2026-08-24
- 决策者：Pi Python 重写项目

## 背景

冻结的 Pi 源码包含 `deepseek-v4-flash` 和 `deepseek-v4-pro`。DeepSeek 的模型版本、能力和价格会独立于 Pi 源码发生变化，因此不能把在线目录更新视为解冻上游基线。

## 决策

- 内建目录只包含文本模型 `deepseek-v4-flash` 和 `deepseek-v4-pro`，默认使用 Pro。
- 两者使用 OpenAI 格式的 `https://api.deepseek.com/chat/completions`，支持 thinking、工具调用、1M context 和最多 384K 输出。
- 不把实验性视觉模型加入 1.0；文本模型收到图片时必须在请求发送前拒绝。
- 静态成本采用 2026-08-24 官方页面的 peak rates，避免在无法表达时段价格的 `ModelCost` 中低估成本。Flash 的 input/output/cache-hit 为 0.44/1.32/0.014 美元每百万 token；Pro 为 1.32/3.96/0.044。
- 目录更新必须使用独立 ADR、离线 fixture、经批准的 live smoke 和独立提交。

## 证据

- 冻结源码：`D:\pi\packages\ai\src\providers\data\deepseek.json` 与 `D:\pi\packages\ai\src\providers\deepseek.ts`，commit `e14afc648e10fb6c527ea88fa627091ada764306`。
- 官方模型和价格：https://api-docs.deepseek.com/quick_start/pricing/
- 官方 Chat Completions 协议：https://api-docs.deepseek.com/api/create-chat-completion/

## 结果

模型选择与能力是可测试的稳定输入；动态计费页面仍是实际费用的最终依据。价格或模型发生变化时，不会悄悄改变既有 Agent 行为。
