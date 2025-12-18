# LAD-IMPL-014/015 与 integration.qa 对齐说明

> 本文档作为 **014/015 任务提示词** 与 **当前集成 QA 实现（integration.qa）** 之间的“桥梁文档”，  
> 用于指导后续实施与验收，避免目标与实现脱节。

- 关联任务：
  - LAD-IMPL-014：链接处理体验（简化版）
  - LAD-IMPL-015：自动化诊断
- 关联实现：
  - [integration/qa](cci:7://file:///d:/lad/local_markdown_viewer_app/integration/qa:0:0-0:0) 包（集成测试套件、报告、CLI、CI 工作流）
  - [.github/workflows/integration-qa.yml](cci:7://file:///d:/lad/local_markdown_viewer_app/.github/workflows/integration-qa.yml:0:0-0:0)
- 关联总览文档：
  - `docs/QA.md`（质量保证 / QA 总览，主入口）
  - 主 `README.md` 中 “质量保证 / QA” 小节（指向 `docs/QA.md`）

---

## 0. 文档范围与不做的事

- 本文 **只做“对齐与映射”**：
  - 把 014/015 提示词中的目标/检查点，逐条对应到 `integration.qa` 已覆盖 / 未覆盖的部分；
  - 给出“下一步如何使用/扩展 integration.qa 支撑 014/015 验收”的建议。
- 不在本文中做的：
  - 不详细展开链接处理业务实现细节（参见各自任务提示词与代码）；
  - 不复述所有 QA/测试细节（参见 `docs/014-体验优化说明-checklist.md` 等）。

---

## 1. 背景与组件总览

### 1.1 任务侧：014 / 015 概要

- LAD-IMPL-014（链接处理体验，简化版）
  - 参考：
    - 《LAD-IMPL-012到015 链接处理系列 - 任务提示词》§4.3
    - 《LAD-IMPL-012到015 统一执行指引与前置条件 V1.0》§4.3
    - 《014-体验优化说明-checklist》
    - 《LAD-IMPL-007到015任务完整提示词 V4.0-简化配置版本》
  - 关注三层：
    1. 链接预览体验（超时/大小限制、加载状态、错误提示）
    2. 性能与埋点（P50/P90/P99、并发数、缓存命中率、错误/重试率）
    3. 配置与热更新体验

- LAD-IMPL-015（自动化诊断）
  - 参考：
    - 《LAD-IMPL-015 自动化诊断 - 任务提示词》
    - 《LAD-IMPL-012到015 统一执行指引与前置条件 V1.0》§4.5
  - 关注四点：
    1. 诊断配置（`features/diagnostics.json` / `app.diagnostics`）
    2. DiagnosticsManager 与热重载
    3. 诊断项目（系统健康、链接处理诊断、性能诊断、安全审计诊断）
    4. 诊断报告与集成（定时任务、告警、API/CLI 输出）

### 1.2 实现侧：integration.qa 概要

- 目录与核心组件：
  - [integration/qa/runners/integration_suite_runner.py](cci:7://file:///d:/lad/local_markdown_viewer_app/integration/qa/runners/integration_suite_runner.py:0:0-0:0)
    - 产出 [IntegrationTestReport](cci:2://file:///d:/lad/local_markdown_viewer_app/integration/qa/runners/integration_suite_runner.py:38:0-47:18)（summary + detailed test_results）
  - [integration/qa/validation.py](cci:7://file:///d:/lad/local_markdown_viewer_app/integration/qa/validation.py:0:0-0:0)
    - [compare_with_legacy(...)](cci:1://file:///d:/lad/local_markdown_viewer_app/integration/qa/validation.py:53:0-109:5)：与 legacy JSON 报告对比
  - [integration/qa/__main__.py](cci:7://file:///d:/lad/local_markdown_viewer_app/integration/qa/__main__.py:0:0-0:0)
    - CLI 入口：`python -m integration.qa`
    - 支持 `--details` / `--format json` / `--compare` / `--write-report`
    - 支持高级退出码开关：
      - `--fail-on-failed-tests` → 退出码 1
      - `--fail-on-success-rate-below` → 退出码 2
      - `--fail-on-compare-diff` → 退出码 3
      - `--fail-on-regression` → 退出码 4
      - `--strict` 组合开关
  - [integration/qa/reporting/writer.py](cci:7://file:///d:/lad/local_markdown_viewer_app/integration/qa/reporting/writer.py:0:0-0:0)（后续可统一管理报告落盘）

- 集成测试内容（来自 IntegrationSuiteRunner）：
  - 模块集成协调测试（SystemIntegrationCoordinator）
  - 监控系统部署测试（MonitoringSystemDeployer）
  - 性能基准测试（PerformanceBenchmarkTester）
  - LinkProcessor 集成准备测试（LinkProcessorIntegrationPreparer）
  - 完善建议对比分析测试（ComparisonAnalysisTool）
  - 系统整体集成测试

- CI 集成：
  - [.github/workflows/integration-qa.yml](cci:7://file:///d:/lad/local_markdown_viewer_app/.github/workflows/integration-qa.yml:0:0-0:0)
  - 在 `windows-latest` 上运行：
    - 安装依赖 → `python -m integration.qa ...` → 写入报告 → 上传 artifact
  - 通过集成 QA CLI 退出码作为 CI gate。

---

## 2. LAD-IMPL-014 与 integration.qa 的对齐

### 2.1 014 目标 → integration.qa 支撑矩阵（概览）

> 本表用于判断：014 的每个维度是否已被 `integration.qa` 覆盖，或需要单独测试/实现。  
> “覆盖情况”列仅描述当前状态，后续可以在“建议动作”列补充 TODO。

| 维度 | 014 任务提示词要求 | integration.qa 当前支撑 | 覆盖情况 | 建议动作 |
|------|--------------------|-------------------------|----------|----------|
| 链接预览行为（小体积资源、超时、大体积截断） | 《014-体验优化说明-checklist》§2.1 | **不直接覆盖 UI/预览行为**；当前集成测试聚焦后台组件与性能 | ❌ | [TODO] 通过 `tests/test_link_preview_and_ux.py` 等补足；集成 QA 可作为性能观察补充 |
| UI 状态与反馈（加载中、错误提示区分） | 《014-体验优化说明-checklist》§2.2 | 不覆盖 UI 状态栏/错误文案 | ❌ | [TODO] 014 自行实现 UI 行为测试；在 QA 文档中标注“由 UI/行为测试负责” |
| 性能指标（P50/P90/P99、错误率、并发数、缓存命中率） | 《014-体验优化说明-checklist》§3.1/3.2；统一指引 §4.3 | PerformanceBenchmarkTester 输出执行时间、成功率、回归报告，已在 [integration_test_report_ci.json](cci:7://file:///d:/lad/local_markdown_viewer_app/integration/qa/artifacts/integration_test_report_ci.json:0:0-0:0) 中提供性能/质量指标 | ✅（部分） | [TODO] 对齐指标命名与阈值，使之与 014 文档中指标一致；在 QA 文档中声明“014 性能基线由 integration.qa 覆盖” |
| 链接处理体验与 013 遗留 CI 用例映射 | 《014-体验优化说明-checklist》§1.2.1/§5.3 | 集成 QA 间接验证 LinkProcessor 集成、性能与监控可用性 | ✅（补充） | [TODO] 在 `docs/014-体验优化说明-checklist.md` 中加入 “integration.qa → 014 性能/集成覆盖” 的映射说明 |
| 配置与热更新体验 | 《014-体验优化说明-checklist》§4 | 集成 QA 可在配置变更后统一验证**整体性能是否仍健康**，但不直接测试单次热更新行为 | ⚠️（间接） | [TODO] 014 自身测试“配置变更 → 行为变化”；同时在变更后跑一轮 integration.qa 作为回归保障 |

>> 注：上表仅为骨架，后续可针对每个维度填充更细致的“集成 QA 字段名”“对应 JSON 路径”等。

- 014 的前置子任务 **T014-00 链接点击基础链路修复** 的详细设计见：`docs/LAD-IMPL-014/T014-00 链接点击修复方案.md`。

### 2.2 集成 QA 报告在 014 验收中的角色

- 建议在 014 验收标准中增加一条：
  - “**014-Perf-01**：在当前配置与实现下，`integration.qa` 报告中的性能基线满足文档规定阈值，且 `regression_detected = false`。”
- 具体落地方式：
  1. 保持 [integration/qa](cci:7://file:///d:/lad/local_markdown_viewer_app/integration/qa:0:0-0:0) 报告结构稳定；
  2. 在 `docs/QA.md` 中说明：
     - “014 体验相关性能与资源约束，由 `integration.qa` 套件生成的 JSON 报告统一验证。”
  3. 在 014 的 checklist 中加入对集成 QA 报告的引用（JSON 字段路径）。

---

## 3. LAD-IMPL-015 与 integration.qa 的对齐

### 3.1 015 诊断目标 → integration.qa 支撑矩阵（概览）

| 诊断维度 | 015 任务提示词要求 | integration.qa 当前支撑 | 覆盖情况 | 建议动作 |
|----------|--------------------|-------------------------|----------|----------|
| 诊断配置（diagnostics.json / app.diagnostics） | 《LAD-IMPL-015 自动化诊断 - 任务提示词》§2.1/2.2 | 集成 QA 目前不读取 diagnostics 配置，由测试 runner 自身控制 | ❌ | [TODO] DiagnosticsManager 设计为可读取 integration.qa 报告作为一种“外部诊断输入”，而非由 integration.qa 依赖 diagnostics |
| 系统健康检查（CPU/内存/磁盘/网络） | 同上 §2.4.1 | 未覆盖 | ❌ | [TODO] 由 015 的诊断模块实现；集成 QA 只提供“应用级链路与性能诊断” |
| 链接处理诊断（validation/performance/security） | 同上 §2.4.3 | 通过 LinkProcessorIntegrationPreparer、ComparisonAnalysisTool、PerformanceBenchmarkTester，对链接处理相关性能/集成状态进行诊断，输出 JSON 报告与建议 | ✅（子集） | [TODO] 在 DiagnosticsManager 中增加一个“集成 QA 报告适配器”，将相关字段映射为 015 的诊断项 |
| 性能诊断与回归检测 | 同上 §2.4.2/§5.2 | 通过 regression_report / quality_metrics / regression_detected 提供对性能回归的诊断与门限判断 | ✅ | [TODO] 015 可直接使用 regression_report 结果，无需重复实现“基准对比”逻辑 |
| 诊断报告生成与集成（定时任务/告警） | 同上 §2.5/§2.5.3/§2.5.4 | integration.qa 提供一次性 CLI + 报告写入能力，尚未集成到 015 的定时/告警体系 | ⚠️（部分） | [TODO] 在 DiagnosticsManager / 定时任务中增加“定期拉取或触发 integration.qa 报告”的机制，作为整体诊断报告的一部分 |

### 3.2 利用 integration.qa 作为 015 的诊断数据源

- 设计建议（骨架）：
  - 在 015 的 DiagnosticsManager 中定义一个抽象接口，例如：
    - `class ExternalDiagnosticsSource(Protocol): ...`
  - 提供一个 `IntegrationQADiagnosticsSource` 实现：
    - 读取 [integration/qa/artifacts/integration_test_report_ci.json](cci:7://file:///d:/lad/local_markdown_viewer_app/integration/qa/artifacts/integration_test_report_ci.json:0:0-0:0) 或其他标准路径；
    - 解析 `test_summary` / `test_results` / `analysis` / `regression_report` / `quality_metrics`；
    - 输出统一的诊断事件/指标结构，供 DiagnosticsManager 使用。
- 优点：
  - 015 不需要重新实现性能基准与回归检测逻辑；
  - 集成 QA 报告成为“链接处理与系统集成”的诊断输入之一，与 Metrics/Logs 等并列。

---

## 4. 文档与目录约定

### 4.1 QA 总览文档

- `docs/QA.md`：统一入口，建议包含：
  - 本项目 QA 目标与层级（单测 → 集成测试 → QA 聚合测试 → 自动化诊断）；
  - 主要 QA 工具与报告：
    - `python -m pytest` / `run_pytests.ps1`
    - `python -m integration.qa`
    - QA 聚合测试（基线报告 + test_qa_all）
  - 对本文件（`LAD-IMPL-014-015-integration-qa-alignment.md`）的链接。

### 4.2 README 中的 QA 指引

- 在主 `README.md` 的“质量保证 / QA” 小节中：
  - 简要说明 QA 分层；
  - 放出指向 `docs/QA.md` 的链接；
  - 可选：列出 `Integration QA` GitHub Actions 工作流的状态徽章/链接。

---

## 5. 后续完善与验收检查表（骨架）

> 本节用于跟踪“对齐工作本身”的完成度，而非 014/015 所有业务实现。

- [ ] 014：在 `docs/014-体验优化说明-checklist.md` 中补充 integration.qa 对齐说明（性能/指标相关）
- [ ] 014：在 QA 文档中声明“014 性能基线验证由 integration.qa 提供”
- [ ] 015：定义 `IntegrationQADiagnosticsSource` 或等效适配层设计
- [ ] 015：在诊断报告中引入 integration.qa 的 regression 与质量指标
- [ ] QA 总览：在 `docs/QA.md` 中加入本对齐文档链接
- [ ] README：在 QA 小节中指向 `docs/QA.md`