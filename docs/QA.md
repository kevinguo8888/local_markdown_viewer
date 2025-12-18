# QA 总览（LAD 本地 Markdown 查看器）

> 本文档是本仓库 QA 的总览入口。
> 目标是把 **测试层次、关键脚本、CI 工作流、报告文件** 说明清楚，并指向更详细的专题文档（如 014/015 对齐说明）。

- 推荐阅读顺序（从总览到专项）：
  1. 本文：`docs/QA.md`
  2. `docs/LAD-IMPL-014/015 与 integration.qa 对齐说明.md`
  3. `docs/014-体验优化说明-checklist.md`
  4. `docs/LAD-IMPL-015-自动化诊断-任务提示词.md`
  5. `docs/LAD-IMPL-012到015-统一执行指引与前置条件V1.0.md`
  6. `docs/013-测试门控与运行指南.md`

---

## 0. 范围与目标

本 QA 体系覆盖：

- 单元 / 功能测试（pytest）
- 集成测试（包含链接处理、监控、性能基准等）
- QA 聚合测试（test_qa_all + 基线报告）
- 集成 QA 套件（`integration.qa` 包 + 报告 + CI gate）
- 后续自动化诊断（LAD-IMPL-015，对 QA 数据的再利用）

**不在本文件详细展开的内容：**

- 各模块业务实现细节（参见对应代码与任务提示词）
- 所有测试用例的逐条说明（参见 `tests/` 目录与各自文档）

---

## 1. QA 分层模型概览

### 1.1 层级一：单元 / 功能测试

- **目标**：验证函数级、模块级逻辑正确性，提供快速反馈。
- **主要入口**：
  - PowerShell 脚本：`./run_pytests.ps1`
  - 直接运行：
    ```bash
    python -m pytest
    ```
- **典型测试文件**：
  - 位于 `tests/` 目录下的常规单测与集成测
  - 链接处理相关用例：`tests/test_link_*.py` 系列等

---

### 1.2 层级二：集成测试（传统 pytest 流）

- **目标**：验证主要组件之间的集成行为（UI ↔ 核心 ↔ 配置 ↔ 监控）。
- **执行方式**：
  - 已封装在 `run_pytests.ps1` 中，作为主测试流程的一部分；
  - CI 中由 `.github/workflows/python-tests.yml` 调用。
- **示例用例（非完整列表）**：
  - `IntegrationTest.test_08_signal_connections`
  - `TestFileResolver.test_resolve_markdown_file`
  - DynamicModuleImporter / PerformanceMetrics 等相关测试

---

### 1.3 层级三：QA 聚合测试（test_qa_all + 基线报告）

- **目标**：聚合多种测试信号，按照 QA 规范（如 4.3.3/4.3.4）做统一检查。
- **入口命令**：
  ```bash
  python -m pytest tests/test_qa_all.py -q
  ```
- **关键输入（基线报告，需纳入 Git）**：
  - 仓库根目录：
    - `integration_test_report.json`
    - `validation_report.json`
  - 用途：
    - 作为 QA 聚合测试的基线数据；
    - CI 中确保历史集成/验证结果可被访问和对比。
- **CI 集成位置**：
  - `.github/workflows/python-tests.yml` 中的 `Run QA gate (4.3.3/4.3.4)` 步骤。

---

### 1.4 层级四：集成 QA 套件（integration.qa）

- **目标**：
  - 以统一入口运行一整套“稳定的集成与性能测试”；
  - 输出结构化 JSON 报告，供人工查看、QA 聚合/诊断系统消费，以及 CI gate 使用。

- **核心代码位置**：
  - `integration/qa/runners/integration_suite_runner.py`
  - `integration/qa/validation.py`
  - `integration/qa/__main__.py`
  - `integration/qa/reporting/writer.py`

- **主要测试内容（由 IntegrationSuiteRunner 编排）**：
  - 模块集成协调测试（SystemIntegrationCoordinator）
  - 监控系统部署测试（MonitoringSystemDeployer）
  - 性能基准测试（PerformanceBenchmarkTester）
  - LinkProcessor 集成准备测试（LinkProcessorIntegrationPreparer）
  - 完善建议对比分析测试（ComparisonAnalysisTool）
  - 系统整体集成测试

- **CLI 用法示例**：
  ```bash
  # 文本摘要输出
  python -m integration.qa

  # 显示详细用例结果
  python -m integration.qa --details

  # JSON 摘要输出到 stdout
  python -m integration.qa --format json

  # 写入 JSON 报告到文件
  python -m integration.qa --details \
    --write-report integration/qa/artifacts/integration_test_report_local.json

  # 与 legacy 报告对比（需要手动提供 legacy JSON 路径）
  python -m integration.qa --details \
    --compare 第二阶段实现提示词/.../outputs/integration_test_report.json
  ```

- **高级退出码开关（CI gate 使用）**：
  - `--fail-on-failed-tests`：存在失败用例时，退出码 = 1
  - `--fail-on-success-rate-below PERCENT`：通过率 < PERCENT 时，退出码 = 2
  - `--fail-on-compare-diff`：legacy 对比失败/不一致时，退出码 = 3
  - `--fail-on-regression`：检测到性能回归时，退出码 = 4
  - `--strict`：等价于同时启用
    `--fail-on-failed-tests` + `--fail-on-compare-diff` + `--fail-on-regression`

> 日常本地开发只需关注 `--details` 与 `--write-report`；
> 高级退出码主要配合 CI 使用，不建议在日常开发时长期开启。

---

### 1.5 层级五：自动化诊断（LAD-IMPL-015，预留）

- **目标**：
  - 统一收集 Metrics / Logs / 配置 / QA 报告等数据；
  - 提供自动化诊断与修复建议；
  - 与监控 / 告警系统对接。
- **参考文档**：
  - `docs/LAD-IMPL-015-自动化诊断-任务提示词.md`
  - `docs/LAD-IMPL-014/015 与 integration.qa 对齐说明.md`
- **与 integration.qa 的关系**：
  - `integration.qa` 生成的 JSON 报告是 **诊断数据源之一**；
  - DiagnosticsManager 可通过适配层消费这些报告，而不是重新实现基准/回归检测逻辑。

---

## 2. 本地开发者快速开始

### 2.1 安装依赖

在仓库根目录执行：

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

---

### 2.2 运行常规测试（pytest + run_pytests.ps1）

- **完整测试（推荐）**：
  ```powershell
  ./run_pytests.ps1
  ```

- **仅收集测试（调试用）**：
  ```powershell
  python -m pytest -vv -s --collect-only tests
  ```

- **直接调用 pytest（自定义参数）**：
  ```bash
  python -m pytest tests
  ```

- **013 测试门控**：
  - 详细说明参见：`docs/013-测试门控与运行指南.md`
  - 简要说明：
    - 通过环境变量 `LAD_RUN_013_TESTS=1` 解禁 013 分组用例；
    - `run_pytests.ps1` 支持 `-Enable013` 参数自动设置相关环境变量。

---

### 2.3 运行集成 QA 套件（integration.qa）

- **快速跑一遍集成套件（文本输出）**：
  ```bash
  python -m integration.qa --details
  ```

- **生成 JSON 报告文件**（便于进一步分析/比对）：
  ```bash
  python -m integration.qa --details \
    --write-report integration/qa/artifacts/integration_test_report_local.json
  ```

- **与 legacy 报告对比**：
  ```bash
  python -m integration.qa --details \
    --compare 第二阶段实现提示词/.../outputs/integration_test_report.json
  ```

---

### 2.4 运行 QA 聚合测试（test_qa_all）

- **用途**：统一检查基线报告是否满足 QA 规则（如 4.3.3/4.3.4）。
- **命令**：
  ```bash
  python -m pytest tests/test_qa_all.py -q
  ```
- **前置条件**：
  - 仓库根目录存在：
    - `integration_test_report.json`
    - `validation_report.json`
  - 且两者已随代码一同纳入 Git。

---

## 3. CI 中的 QA 工作流

### 3.1 `Python Tests` 工作流

- **配置文件**：`.github/workflows/python-tests.yml`
- **作用**：
  - 在 `windows-latest` 上：
    - 安装依赖；
    - 输出 Python/包环境信息；
    - 检查 psutil/Flask/Markdown/PyQt/QtWebEngine 等依赖；
    - 调用 `./run_pytests.ps1` 跑常规测试；
    - 运行 QA gate（4.3.3/4.3.4）：`python -m pytest tests/test_qa_all.py -q`；
    - 上传 pytest 日志与收集输出。
- **触发方式**：push / pull_request / workflow_dispatch（详见配置文件）。

---

### 3.2 `Integration QA` 工作流

- **配置文件**：`.github/workflows/integration-qa.yml`
- **作用**：
  - 在 `windows-latest` 上：
    - 设置 `PYTHONIOENCODING=utf-8`（避免中文日志编码问题）；
    - 安装依赖；
    - 输出环境信息（Python 版本、pip 列表、当前目录等）；
    - 运行集成 QA 套件：
      ```powershell
      python -m integration.qa --details `
        --write-report integration/qa/artifacts/integration_test_report_ci.json `
        --strict `
        --fail-on-success-rate-below 100
      ```
    - 上传 `integration/qa/artifacts/integration_test_report_ci.json` 作为 artifact。
- **退出码语义**：
  - 0：所有启用的 gate 条件均满足；
  - 1：存在失败用例（且启用 `--fail-on-failed-tests` 或 `--strict`）；
  - 2：通过率低于指定阈值（`--fail-on-success-rate-below`）；
  - 3：legacy 报告对比失败/不一致（启用 `--fail-on-compare-diff`/`--strict` 且指定 `--compare` 时）；
  - 4：检测到性能回归（启用 `--fail-on-regression` 或 `--strict`）。

---

### 3.3 推荐的 CI gate 策略（建议）

- 对 PR / main 分支：
  - **必须通过**：
    - `Python Tests` 工作流；
    - `Integration QA` 工作流。
  - 长期规划（结合 014/015）：
    - `Python Tests`：覆盖单测 + 传统集成测试 + QA 聚合 gate；
    - `Integration QA`：专注于“稳定的端到端集成与性能基线”；
    - 自动化诊断（015）：在上述基础上增加更高阶的健康/风险判断。

---

## 4. 报告与关键文件一览

### 4.1 QA 基线报告（供 QA 聚合测试使用）

- 仓库根目录：
  - `integration_test_report.json`
  - `validation_report.json`
- 说明：
  - 作为当前系统的“基线 QA 结果”，被 `tests/test_qa_all.py` 消费；
  - 必须纳入 Git，以便 CI 稳定访问；
  - 更新这些基线时，建议：
    1. 本地跑一轮 integration.qa 或相关脚本生成新报告；
    2. 人工校对差异；
    3. 更新基线文件并在提交说明中记录原因。

---

### 4.2 集成 QA 报告（integration.qa）

- 路径示例：
  - CI 中：`integration/qa/artifacts/integration_test_report_ci.json`
  - 本地调试：`integration/qa/artifacts/integration_test_report_local.json`（示例）
- 内容结构（简要）：
  - `test_summary`：总用例数、通过/失败/跳过、成功率、总耗时等；
  - `timestamp`：执行时间戳；
  - `test_results`（在 `--details` 时）：每个测试的名称、类别、耗时、状态、错误信息等；
  - 部分测试结果中还包含：`baseline` / `analysis` / `regression_report` / `quality_metrics` 等诊断信息。

---

### 4.3 对齐与专题文档

- `docs/LAD-IMPL-014/015 与 integration.qa 对齐说明.md`
  - 描述 014/015 任务提示词与 `integration.qa` 套件之间的映射；
  - 标明哪些目标已由集成 QA 覆盖，哪些仍需 014/015 自己负责。
- `docs/014-体验优化说明-checklist.md`
  - 追踪 014 实际落地项，与 CI/测试用例的映射。
- `docs/LAD-IMPL-015-自动化诊断-任务提示词.md`
  - 自动化诊断系统的任务目标、技术方案与验收标准。
- `docs/LAD-IMPL-012到015-统一执行指引与前置条件V1.0.md`
  - 012–015 系列任务的统一执行指引与顺序关系。
- `docs/013-测试门控与运行指南.md`
  - 013 测试分组与门控策略、环境变量、运行脚本说明。

---

## 5. 与 LAD-IMPL-014/015 的关系（摘要）

> 详细对齐请见：`docs/LAD-IMPL-014/015 与 integration.qa 对齐说明.md`。这里只保留“摘要版”。

- **对 014（链接处理体验）**：
  - `integration.qa`：
    - 提供链接处理及相关组件的 **集成与性能基线**；
    - 输出 `regression_report` / `quality_metrics`，可用于验证“体验相关性能约束”是否满足。
  - 014 仍需自行实现和测试：
    - 预览行为（超时/大小限制/截断）；
    - UI 状态与反馈（加载中、错误提示文案）；
    - 配置与热更新的行为一致性。

- **对 015（自动化诊断）**：
  - `integration.qa`：
    - 已提供一套可复用的“性能与集成诊断 + 报告 + gate”能力；
    - 其 JSON 报告可作为 DiagnosticsManager 的一类外部诊断输入。
  - 015 仍需完成：
    - diagnostics 配置体系；
    - DiagnosticsManager 与热重载；
    - 系统健康检查（CPU/内存/磁盘/网络等）；
    - 定时任务、告警与更上层的诊断规则。

---

## 6. 常见问题（FAQ）

- **Q：本地跑 `python -m integration.qa` 会不会很慢？**  
  A：性能基准测试可能耗时数十秒，是预期行为。CI 已验证在 `windows-latest` 环境中可接受。

- **Q：CI 中看到中文日志编码错误怎么办？**  
  A：`Integration QA` 工作流已设置 `PYTHONIOENCODING=utf-8`。如需在其他工作流中打印中文，请类似设置。

- **Q：如何排查集成 QA 失败？**  
  1. 下载 CI 上传的 `integration_test_report_ci.json`（或本地生成的报告）；
  2. 查看 `test_summary` 中失败用例数量；
  3. 在 `test_results` 中定位具体失败用例及错误信息；
  4. 根据对应模块与任务提示词（如 014/015）进行修复。

- **Q：什么时候需要更新根目录的 `integration_test_report.json` / `validation_report.json`？**  
  A：当系统整体行为/质量水位有“有意识的提升或调整”时，而不仅是小 bugfix。更新前建议：
  - 对比新旧报告；
  - 在提交说明中记录“为何更新基线”。

---

> 如需对 QA 体系进行扩展或调整，请同时更新：
> `docs/QA.md` 与 `docs/LAD-IMPL-014/015 与 integration.qa 对齐说明.md`，保持任务提示词与实现的一致性。
