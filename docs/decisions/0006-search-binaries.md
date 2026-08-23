# ADR 0006：固定并校验搜索工具二进制

- 状态：Accepted
- 日期：2026-08-24
- 决策者：Pi Python 重写项目

## 背景

冻结的 Pi 源码会在系统缺少 `rg` 或 `fd` 时查询 GitHub 最新版本并下载，但没有校验发布资产。这样会让相同的 Python 版本在不同日期得到不同二进制，也无法证明下载内容没有被替换。

## 决策

- 始终优先使用 PATH 中已有的 `rg`、`fd` 或 `fdfind`。
- 托管下载固定为 ripgrep 15.2.0 和 fd 10.4.2，不在运行时查询“最新版本”。
- 只支持 Windows/Linux 的 x86_64 与 aarch64 官方资产；macOS 和其他架构明确拒绝。
- 下载完成后、解压前校验 GitHub Release API 发布的 SHA-256；不匹配时不创建或改写缓存二进制。
- 只从归档中读取唯一、名称匹配的普通文件，并原子写入缓存；不按归档路径展开文件。
- offline 模式只检查系统 PATH 和现有缓存，绝不调用下载器。
- 升级版本或哈希必须使用新 ADR、离线归档测试和独立提交。

## 固定资产

| 工具 | 平台 | 架构 | 资产 | SHA-256 |
|---|---|---|---|---|
| rg | Windows | x86_64 | `ripgrep-15.2.0-x86_64-pc-windows-msvc.zip` | `71b2fef860abe467217a538ff31de02f5258807c0129f771846f87bd029aafc5` |
| rg | Windows | aarch64 | `ripgrep-15.2.0-aarch64-pc-windows-msvc.zip` | `e4abca10c3a64ebea742667dd7009449d49403db5460dd6873e389fa2945360f` |
| rg | Linux | x86_64 | `ripgrep-15.2.0-x86_64-unknown-linux-musl.tar.gz` | `33e15bcf1624b25cdd2a55813a47a2f95dbe126268203e76aa6a585d1e7b149c` |
| rg | Linux | aarch64 | `ripgrep-15.2.0-aarch64-unknown-linux-gnu.tar.gz` | `a740b91c82eaf9914cfedd353572f2791cbe0162c84101ee0951058f4dcbc90d` |
| fd | Windows | x86_64 | `fd-v10.4.2-x86_64-pc-windows-msvc.zip` | `b2816e506390a89941c63c9187d58a3cc10e9a55f2ef0685f9ea0eccaf7c98c8` |
| fd | Windows | aarch64 | `fd-v10.4.2-aarch64-pc-windows-msvc.zip` | `4f9110c2d5b33a7f760bfa5510f4c113d828109f7277d421b1053a9943c0fc92` |
| fd | Linux | x86_64 | `fd-v10.4.2-x86_64-unknown-linux-gnu.tar.gz` | `def59805cd14b5651b68990855f426ad087f3b96881296d963910431ba3143c8` |
| fd | Linux | aarch64 | `fd-v10.4.2-aarch64-unknown-linux-gnu.tar.gz` | `6c51f7c5446b3338b1e401ff15dc194c590bb2fa64fd43ff3278300f073adec5` |

## 证据

- 冻结源码：`D:\pi\packages\coding-agent\src\utils\tools-manager.ts`，commit `e14afc648e10fb6c527ea88fa627091ada764306`。
- ripgrep 官方发布：https://github.com/BurntSushi/ripgrep/releases/tag/15.2.0
- fd 官方发布：https://github.com/sharkdp/fd/releases/tag/v10.4.2
- 哈希来源：上述 GitHub Release API 的资产 `digest` 字段，核验日期 2026-08-24。

## 结果

系统管理员仍可通过 PATH 选择自己的工具版本；自动下载则成为可复现、可审计且可离线阻断的受控行为。这是相对冻结 TypeScript 实现的安全性增强，分类为 Intentional divergence。
