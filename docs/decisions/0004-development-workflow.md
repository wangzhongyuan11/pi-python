# ADR 0004：阶段化、测试先行的开发工作流

- 状态：Accepted
- 日期：2026-08-15
- 决策者：Pi Python 重写项目

## 背景

这是跨 Provider、Agent、持久化、shell、文件系统、TUI 和 Extension 的多阶段重写。一次性实现会让行为偏差和安全回归无法定位。冻结上游仓库还包含可能修改文件的检查命令，不能把 oracle 检查变成对上游的写操作。

## 决策

### 任务单位

- `tasks/plan.md` 定义阶段和验收；原子任务表定义当前执行顺序。
- Phase 0 后使用短分支 `phase/NN-name`；一个任务只改变一个可观察行为。
- 每个实现任务遵循：红测 -> 最小实现 -> 聚焦验证 -> 阶段回归 -> review。
- 不为未来需求提前增加抽象；公共接口先写契约和 consumer test。

### 默认验证

- Python 3.12+，Hatchling、uv、Ruff、Pyright strict、pytest。
- 所有默认测试离线运行；清空 API key、HOME、用户配置、缓存和 Git 全局影响。
- Provider/Agent/CLI 测试优先使用 FakeProvider、FakeTool、FakeClock、临时 workspace 和 isolated home。
- 真实 DeepSeek smoke 使用独立 marker；每一次运行前都需用户明确批准。
- 关键 wire 使用 golden/round-trip 测试；关键行为使用冻结 TypeScript fixture/oracle 的规范化差分测试。

### 上游 oracle 规则

- `D:\pi` 固定在 `e14afc648e10fb6c527ea88fa627091ada764306`，只读访问源码、测试和已有 fixture。
- 禁止对 `D:\pi` 运行 formatter、codegen、`npm run check` 或其他会写文件的命令。
- 不运行上游 build 或完整 test suite；若未来确需执行某个只读测试，先获得用户批准并证明不会访问真实 endpoint/credential。
- 每次 oracle 比较记录提交、输入、规范化规则和差异，不依赖当前时间、网络或用户目录。

### Git 与并行协作

- 开始前检查 `git status`；保留并适配其他 agent/用户的变更。
- 只修改任务明确拥有的文件；不格式化或重构相邻文件。
- 不使用破坏性 reset/checkout，不擅自 commit、push 或创建 PR。
- Phase gate 通过后才进入下一阶段；发布候选必须从仓库外、全新 HOME 安装 wheel 验证。

### Phase 0 远端保护豁免

- Phase 0 代码、CI 和 secret scan 已直接建立并推送到远端 `main`。
- 2026-08-21，用户明确决定不启用 GitHub required checks 和禁止直推规则。
- 该豁免只改变远端治理设置；原子任务、本地门禁、CI 矩阵和每阶段停止验收规则继续执行。

## 源码证据

- 上游 `npm run check` 包含 `biome check --write`，会改写仓库：`D:\pi\package.json:L18 @ e14afc648`。
- 上游协作规则明确 code change 才运行 check，且 build/full test 需用户请求：`D:\pi\AGENTS.md:L31-L33 @ e14afc648`。
- 上游禁止未经请求 commit：`D:\pi\AGENTS.md:L40 @ e14afc648`。
- 上游完整 test script 会递归 workspace：`D:\pi\package.json:L33 @ e14afc648`，不适合作为默认只读 oracle。

## 备选方案

### 先实现完整产品，再补测试

拒绝。流式事件顺序、Session 崩溃点和并发工具完成顺序很难在事后可靠补齐。

### 每次同步上游并跑全量 npm 检查

拒绝。它破坏冻结基线，且检查本身会写文件。

### 只做端到端测试

拒绝。真实 Provider 和终端环境不确定，无法精确定位 schema、状态机或持久化差异。

## 结果

- 好处：每一步都有可复现证据，失败可定位到一个契约或阶段。
- 代价：前期文档和 fixture 成本更高；live 能力验证晚于核心离线切片。
- 完成定义：实现、类型检查、离线测试、安全断言、兼容矩阵状态和文档必须同步完成。
