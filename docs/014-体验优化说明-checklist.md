# LAD-IMPL-014：链接处理体验 - 实施 Checklist（草案骨架）

> 角色定位：本清单用于**跟踪本仓库中 014 相关的实际落地项**，  
> 与以下“任务提示词 / 统一指引”配合使用：
> - 《LAD-IMPL-012到015 统一执行指引与前置条件 V1.0》§4.3
> - 《LAD-IMPL-012到015 链接处理系列 - 任务提示词》§4.3、§2.7、§2.9
> - （参考）《LAD-IMPL-015 自动化诊断 - 任务提示词》

---

## 0. 元信息与关联范围

- **任务 ID**：LAD-IMPL-014（链接处理体验，简化版）
- **版本**：v0.1 草案（仅供本阶段规划使用）
- **本仓库范围**：采用“完成标准 A（简化版）”，当前仅落地 T014-00 链接点击基础链路修复；预览行为、性能指标与配置热更新等重体验项保留为后续任务。
- **关联任务**：
  - 前置：LAD-IMPL-012（链接接入）、LAD-IMPL-013（安全）
  - 并行/后续：LAD-IMPL-015（自动化诊断）、LAD-IMPL-015B（验收）
- **参考文档对齐**：
  - [ ] 已阅读并对齐《统一执行指引》§4.3（体验）
  - [ ] 已阅读并对齐《链接处理系列-任务提示词》§4.3（体验）、§2.7/§2.9（性能指标）

---

## 1. 前置条件与环境确认（与 013 遗留问题对齐）

### 1.1 配置 / 代码存在性

- [ ] `config/app_config.json` 中存在（或可缺省回落的）`link_processing` 段
- [ ] `config/features/link_processing.json` 存在且结构符合约定
- [ ] `config/runtime/performance.json` 存在（或使用 `features/logging.json.performance` 兜底）
- [ ] 核心代码存在且可导入：
  - [ ] `core/link_processor.py`
  - [ ] `ui/content_viewer.py`（LPCLICK 路径）
  - [ ] `core/performance_metrics.py`
  - [ ] [utils/config_manager.py](cci:7://file:///d:/lad/LAD_md_ed2/local_markdown_viewer/utils/config_manager.py:0:0-0:0)

### 1.2 与 013 遗留 CI / 线上问题的收尾

- [ ] 链接点击相关 CI 测试全部通过（列出关键用例）：
  - [ ] `IntegrationTest.test_08_signal_connections`（file_selected 信号链路）
  - [ ] `TestFileResolver.test_resolve_markdown_file`（路径规范化）
  - [ ] `test_successful_function_mapping` / `test_missing_functions` / `test_non_callable_functions`（DynamicModuleImporter 稳定回退）
  - [ ] `test_enable_monitoring_creates_metrics`（metrics/bridge 目录）
- [ ] 相关线上错误日志已消除或降为预期告警级别（记录链接到监控/日志面板）

#### 1.2.1 013 遗留 CI 用例 → 014 前置体验项映射

| CI 测试 | 主要关注点 | 对应 014 体验项 |
|---------|------------|-----------------|
| `IntegrationTest.test_08_signal_connections` | MainWindow / FileTree 文件点击后是否正确发出 `file_selected`，驱动右侧内容刷新 | §2.2 UI 状态与反馈；§5.2 LPCLICK 行为用例 |
| `TestFileResolver.test_resolve_markdown_file` | 路径规范化一致性，确保点击文件或文内链接时总能打开**正确的** markdown 文件 | §1.1 路径配置前置；§2.1 预览行为定义（小体积资源） |
| `test_successful_function_mapping` / `test_missing_functions` / `test_non_callable_functions` | DynamicModuleImporter 在模块不可用/函数不完整时的稳定回退，避免渲染/预览直接失败 | §2.1 预览成功/失败体验；§3.1 错误计数与重试率 |
| `test_enable_monitoring_creates_metrics` | metrics/bridge 目录存在且可写，使体验相关性能指标可以被采集 | §3.1 指标与埋点列表（link_processing_latency 等）；§3.2 性能体验约束 |

---

## 2. 链接预览体验（行为层）

> 对应统一指引 §4.3：“链接预览（超时/大小限制）、加载状态、错误提示优化”

### 2.1 预览行为定义与实现

- [ ] **小体积资源**：在 `preview.timeout_ms` 内完成预览  
      - 线下验证：单测 / 集成测试  
      - 线上验证：延迟指标 P50/P90/P99 正常
- [ ] **大体积资源**：内容按 `preview.max_size_kb` 截断，并提示“内容过大”或等价信息
- [ ] **超时场景**：请求超出 `preview.timeout_ms` 时：
  - [ ] 及时终止请求
  - [ ] 给出明确超时提示（非泛化“加载失败”）
- [ ] **非法 / 不安全链接**（依赖 013 安全规则）：
  - [ ] 预览阶段直接拒绝
  - [ ] 提示中包含“安全原因”（而非单纯“失败”）
  - [ ] 记录相应安全审计事件（参照 013 日志格式）

### 2.2 UI 状态与反馈

- [ ] 触发 LPCLICK / 链接点击时，出现**加载中状态**：
  - [ ] 状态栏 / 指示器变化可见
  - [ ] 并在成功或失败后恢复
- [ ] 预览成功时：
  - [ ] 内容区更新
  - [ ] 状态栏可选展示“加载完成” / 耗时摘要
- [ ] 预览失败时：
  - [ ] 失败原因有区分度（超时 / 不安全 / 网络错误 / 解析错误）
  - [ ] 有可选入口定位到 error_history 或日志详情（如果启用）

---

## 3. 性能与资源体验（埋点与感知）

> 对应“性能埋点：P50/P90/P99、并发检查数、缓存命中率、错误/重试率”

### 3.1 指标与埋点列表

| 项目 | 指标名称（建议） | 线下验证方式 | 线上验证方式 | 状态 |
|------|------------------|--------------|--------------|------|
| 链接解析延迟 | `link_processing_latency` (Histogram) | 单测中 mock metrics 并断言记录次数/label | 监控看 P50/P90/P99 | [ ] |
| 错误计数 | `link_processing_errors` (Counter) | 制造失败场景，看计数 +1 | 告警阈值配置 | [ ] |
| 当前并发数 | `active_link_checks` (Gauge) | 压测/模拟并发，检查数值变化 | 仪表盘趋势图 | [ ] |
| 缓存命中率 | `cache_hit_rate` (Gauge) | 重复请求同一链接，命中率上升 | 常态运行监控 | [ ] |
| 重试率 | `link_processing_retries` (Counter/Gauge) | 模拟可重试错误 | 告警或报表 | [ ] |

### 3.2 性能体验约束

- [ ] 线下基准：  
  - [ ] 小规模样本下 P99 延迟满足文档/需求给定的阈值（可以先写“暂定阈值 TBD”）
- [ ] 资源占用无明显尖峰（结合 011 性能监控）

---

## 4. 配置与热更新体验

> 聚焦 `link_processing` / `preview` / `performance` 等配置在“体验上的”表现

### 4.1 核心配置项清单

- [ ] `link_processing.enabled`：关闭时：
  - [ ] 链接点击退化为默认行为（或禁用），有明确提示
- [ ] `link_processing.preview.enabled`：关闭时：
  - [ ] 不触发网络预取，仅进行基础跳转/打开
- [ ] `link_processing.preview.timeout_ms`：
  - [ ] 合理范围有文档说明（例如 1–30s）
  - [ ] 超出范围的配置能在启动或诊断阶段被发现
- [ ] `link_processing.preview.max_size_kb`：
  - [ ] 配置变更后，预览行为实时生效（可选：需要重新加载）

### 4.2 热更新与体验一致性

- [ ] 通过 ConfigManager 修改相关配置后：
  - [ ] 不需要重启即可生效（若设计如此）
  - [ ] 不会触发异常（监听器签名正确）
- [ ] 线下有测试覆盖：
  - [ ] 模拟配置文件变更 → 链接预览行为同步变化

---

## 5. 测试用例与 CI 映射（线下视角）

> 这里不要求你一次写完测试，只做**“应该有哪几类测试”**的清单

### 5.1 单元 / 组件测试

- [ ] `tests/test_link_preview_and_ux.py`（新建/补充）：
  - [ ] `test_preview_small_resource_success`
  - [ ] `test_preview_timeout_behavior`
  - [ ] `test_preview_oversize_truncation`
  - [ ] `test_preview_security_blocked_link`
  - [ ] `test_preview_cache_hit_behavior`

### 5.2 集成 / UI 行为测试

- [ ] 覆盖 LPCLICK 全链路：
  - [ ] 用例：点击 markdown 页面内链接 → 预览行为 & 状态栏反馈
- [ ] 与 013 安全规则的集成：
  - [ ] 用例：安全配置变化对预览行为的影响

### 5.3 与现有 CI 测试的挂钩

- [ ] 已对 013 遗留 CI 用例建立“CI → 014 体验项”映射（见 §1.2.1）
- [ ] 后续新增/扩展的链接处理 CI / 集成测试，需补充到本节清单，并同步更新 §1.2.1 映射表
- [ ] 重点关注以下几类测试：
  - [ ] `IntegrationTest.test_08_signal_connections`（驱动文件选择与预览刷新）
  - [ ] `TestFileResolver.test_resolve_markdown_file`（路径解析与文件定位）
  - [ ] `test_successful_function_mapping` / `test_missing_functions` / `test_non_callable_functions`（渲染模块回退与稳定性）
  - [ ] `test_enable_monitoring_creates_metrics`（性能指标采集链路可用性）

---

## 6. 与 015/015B 的接口与可诊断性（只列接口点，不展开实现）

- [ ] 为 015 预留的“体验诊断项”：
  - [ ] 指标是否存在/稳定（见 §3.1）
  - [ ] 错误提示/状态是否覆盖典型故障场景
- [ ] 为 015B 验收提供的输入：
  - [ ] 一份体验角度的测试清单（可由本 checklist 精简生成）
  - [ ] 一份“体验指标基线”记录（例如当前 P50/P95/P99）

---

## 7. 执行状态追踪（本项目本阶段）

> 这一节主要给你用来打勾和记备注

- [ ] 014 前置条件全部满足（§1）
- [ ] 关键体验行为已定义并实现（§2）
- [ ] 性能与资源指标已接入并在 CI/本地可观测（§3）
- [ ] 配置与热更新路径稳定（§4）
- [ ] 对应测试已编写并在 CI 通过（§5）
- [ ] 与 015/015B 接口点已对齐（§6）
- 备注：
  - 本仓库当前阶段：仅完成 T014-00 链接点击基础链路修复；§2–§6 中的大部分条目保留为后续 014/015 子任务的规划输入。
  - 如后续扩展体验与指标实现，再按实际落地情况在本 checklist 上逐项打勾。
