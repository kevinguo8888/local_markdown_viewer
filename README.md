# 本地Markdown文件渲染器
 
[![Python Tests](https://github.com/kevinguo8888/local_markdown_viewer/actions/workflows/python-tests.yml/badge.svg)](https://github.com/kevinguo8888/local_markdown_viewer/actions/workflows/python-tests.yml)
[![Integration QA](https://github.com/kevinguo8888/local_markdown_viewer/actions/workflows/integration-qa.yml/badge.svg)](https://github.com/kevinguo8888/local_markdown_viewer/actions/workflows/integration-qa.yml)

## 项目简介

基于PyQt5的本地Markdown文件渲染和文档管理工具，支持多种文件类型的预览和渲染。

## 快速链接

- [013 测试门控与运行指南](docs/013-测试门控与运行指南.md)
- [质量保证 / QA 总览](docs/QA.md)
- [LAD-IMPL-014/015 与 integration.qa 对齐说明](docs/LAD-IMPL-014/015 与 integration.qa 对齐说明.md)

## 质量保证 / QA

- 完整 QA 分层与流程说明见：[`docs/QA.md`](docs/QA.md)
- 关键 CI 工作流：
  - [Python Tests](.github/workflows/python-tests.yml)
  - [Integration QA](.github/workflows/integration-qa.yml)

## 功能特性

- 二栏布局：左侧文件树，右侧文档内容显示
- 智能文件解析：自动识别文件类型，支持Markdown渲染和原始内容预览
- 直接复用markdown_processor.py组件
- 可配置的界面样式和逻辑
- 支持本地文件拖拽打开
- 多标签/多窗口支持（可扩展）

## 系统要求

- Python 3.7+
- PyQt5 5.15.0+
- Windows/macOS/Linux

## 安装说明

1. 克隆项目到本地
2. 安装依赖包：
   ```bash
   pip install -r requirements.txt
   ```

## 使用方法

运行主程序：
```bash
python main.py
```

### 部署与快速入口（4.3.4）

- 快速入口脚本：`local_markdown_viewer/deploy.ps1`
- 用法：
  ```powershell
  # 使用默认/样例配置并运行聚合门禁
  ./local_markdown_viewer/deploy.ps1

  # 指定配置文件
  ./local_markdown_viewer/deploy.ps1 -ConfigPath ./local_markdown_viewer/第二阶段实现提示词/本地Markdown文件渲染程序-重构过程-第二阶段核心功能-06_后期完善-实现提示词/outputs/deploy/deploy_config.sample.json

  # 跳过测试（不建议在生产前跳过）
  ./local_markdown_viewer/deploy.ps1 -SkipTests
  ```

- 环境与编码建议：
  - CI/本地均建议设置：`PYTHONUTF8=1` 和 `PYTHONIOENCODING=utf-8`
  - 部署脚本会自动设置上述环境变量，解决 Windows GBK 控制台导致的编码问题

#### 干跑（WhatIf）

- 仅执行检查，不落地变更：
  ```powershell
  ./local_markdown_viewer/deploy.ps1 -WhatIf
  # 干跑且跳过测试
  ./local_markdown_viewer/deploy.ps1 -WhatIf -SkipTests
  ```

#### 回退（Rollback）

- 按标准回退路径自动关闭集成与监控，并备份原配置：
  ```powershell
  ./local_markdown_viewer/deploy.ps1 -Rollback
  # 干跑回退
  ./local_markdown_viewer/deploy.ps1 -Rollback -WhatIf
  ```

## 项目结构

```
local_markdown_viewer/
├── main.py                          # 程序入口
├── config/                          # 配置文件目录
│   ├── app_config.json             # 应用配置
│   ├── ui_config.json              # 界面配置
│   └── file_types.json             # 文件类型配置
├── ui/                              # 用户界面模块
│   ├── main_window.py              # 主窗口类
│   ├── file_tree.py                # 文件树组件（待实现）
│   ├── content_viewer.py           # 内容显示组件（待实现）
│   └── styles/                     # 样式文件
├── core/                            # 核心功能模块
│   ├── file_resolver.py            # 文件解析模块（待实现）
│   ├── markdown_renderer.py        # Markdown渲染器（待实现）
│   └── content_preview.py          # 内容预览器（待实现）
├── utils/                           # 工具模块
│   ├── config_manager.py           # 配置管理器
│   ├── file_utils.py               # 文件工具（待实现）
│   └── path_utils.py               # 路径工具（待实现）
├── resources/                       # 资源文件
│   ├── icons/                      # 图标资源
│   └── templates/                  # 模板文件
└── tests/                          # 测试文件
```

## 开发状态

当前版本：v1.0.0
开发阶段：第一阶段 - 基础框架

### 已完成
- [x] 项目结构创建
- [x] 配置文件设计
- [x] 配置管理器实现
- [x] 主窗口基础框架
- [x] 程序入口文件

### 待实现
- [ ] 文件树组件
- [ ] 内容显示组件
- [ ] 文件解析模块
- [ ] Markdown渲染器
- [ ] 内容预览器
- [ ] 文件工具
- [ ] 路径工具

## 配置说明

### 应用配置 (app_config.json)
- 应用基本信息
- 窗口设置
- 文件树配置
- Markdown配置
- 日志配置

### 界面配置 (ui_config.json)
- 布局设置
- 颜色主题
- 字体配置
- UI行为设置

### 文件类型配置 (file_types.json)
- 支持的文件类型
- 渲染方式
- 预览模式
- 文件图标

## 贡献指南

1. Fork 项目
2. 创建功能分支
3. 提交更改
4. 推送到分支
5. 创建 Pull Request

### PyQt 测试初始化与降噪指南

- 统一初始化策略
  - 测试会话启动时自动构造 `QApplication([])`，避免在未构造 QApplication 前创建 `QWidget/QMainWindow`。
  - 默认不设置 `QT_QPA_PLATFORM`；使用 `QT_OPENGL=software`，并设置 `QTWEBENGINE_DISABLE_SANDBOX=1` 与 `QTWEBENGINE_CHROMIUM_FLAGS="--no-sandbox --disable-gpu --single-process"`，以支持无头/CI 环境并禁用 GPU/sandbox。
  - 采用 `QT_LOGGING_RULES="*.debug=false;qt.qpa.*=false;qt.text.*=false;qt.fonts.*=false"` 降低 Qt 控制台噪声。
- 本地与 CI 一致化
  - 已在 `tests/conftest.py` 与运行脚本中统一设置上述策略。
  - `run_pytests.ps1` 默认不设置 `QT_QPA_PLATFORM`，设置前述软件 OpenGL 与禁用 sandbox/GPU 的变量，并开启 `-W error` 门禁（警告即错误）。
- 兼容性与提示
  - 个别 Qt 运行时提示（如字体目录缺失）可能直接输出到 stderr，非 Python 警告，不影响 `-W error`；如需进一步静音，可在环境层面补充字体或调整日志规则。

### 013 测试门控与运行指南

- 门控变量
  - 通过环境变量 `LAD_RUN_013_TESTS=1` 解禁 013 分组用例；默认不启用（门控关闭）。
- 脚本支持
  - `run_pytests.ps1` 新增参数 `-Enable013`，启用后自动导出 `LAD_RUN_013_TESTS=1`。
  - `scripts/run_full_mode_tests.ps1` 新增参数 `-Enable013`，用于全模式/集成验证时解禁 013 用例。
  - 两个脚本均统一设置：`QT_QPA_PLATFORM=offscreen` 与 `QT_LOGGING_RULES="*.debug=false;qt.qpa.*=false;qt.text.*=false;qt.fonts.*=false"`，保证本地与 CI 行为一致。
- 直接运行示例（PowerShell）
  - 单次解禁运行：
    ```powershell
    $env:LAD_RUN_013_TESTS="1"; $env:LAD_TEST_MODE="1";
    $env:QT_OPENGL="software"; $env:QTWEBENGINE_DISABLE_SANDBOX="1";
    $env:QTWEBENGINE_CHROMIUM_FLAGS="--no-sandbox --disable-gpu --single-process";
    $env:QT_LOGGING_RULES="*.debug=false;qt.qpa.*=false;qt.text.*=false;qt.fonts.*=false";
    python -u -m pytest -vv -W error -s tests/test_link_processor_external.py
    ```
  - 脚本方式：
    ```powershell
    # 常规回归
    ./run_pytests.ps1 -Enable013
    
    # 全模式关键用例集
    ./scripts/run_full_mode_tests.ps1 -Enable013
    ```
  
注：日志中可能偶见类似 “This plugin does not support createPlatformOpenGLContext!” 的 Qt 插件自带提示，该类输出为底层 stderr 提示，非 Python 警告，不受 `-W error` 门禁影响；已通过 `offscreen` 和 `QT_LOGGING_RULES` 最大化降噪，通常可忽略。

## 许可证

本项目采用 MIT 许可证。

## 作者

LAD Team

## 更新日志

### v1.0.0 (2025-01-08)
- 初始版本
- 基础框架实现
- 配置管理系统
- 主窗口布局

---

## 注释示例使用约定（简版）

### 目的
为新成员提供"统一异常/缓存通配删除"最小引用范式，减少实现分歧；示例仅作参考，不参与运行。

### 位置
- `core/markdown_renderer.py` 文件尾部
- `core/link_processor.py` 文件尾部  
- `core/content_preview.py` 文件尾部

均带前缀"文档注释：引用示例（仅供参考，非运行代码）"。

### 用法
1. 对照复制必要的 import 与调用方式
2. 替换为当前模块的真实变量与逻辑
3. 若已有统一适配层（如 Cache 适配器），以项目现有接口为准

### AI协作注意
AI 生成代码时应将该注释视作"范式提示"，优先遵循当前模块已存在的接口/约束，不强制注入示例代码。

### 相关工具
- `core/errors.py` - 统一错误类型定义
- `cache/delete_pattern_utils.py` - 缓存通配删除工具

## 项目进展

当前状态概览：012–014 已按本仓库约定范围完成并阶段封盘；015、016 处于“规划与清单已落盘、实现待后续推进”的阶段。

### 最新更新 (2025-09-01)
- **核心功能优化**: 完成LAD-IMPL-004/005/006任务，优化DynamicModuleImporter和HybridMarkdownRenderer
- **P1级别改进**: 实施缓存持久化精简和接口契约表完善
- **文档体系标准化**: 创建V3.2完整提示词文档，建立标准化执行流程
- **新会话准备**: 完成执行准备方案，可启动LAD-IMPL-007任务

### 技术状态
- **核心功能**: 稳固且已验证
- **缓存机制**: 优化完成，支持持久化
- **接口契约**: 标准化完成
- **文档体系**: 完备且标准化

### 详细变更记录
请参见 [CHANGELOG.md](CHANGELOG.md) 和 [2025-09-01工作总结报告.md](docs/2025-09-01工作总结报告.md) 

## 历史发布

- [v2025.11.06](https://github.com/kevinguo8888/lad_markdown_viewer/releases/tag/v2025.11.06) - Warnings as Errors 门禁落地（321 passed, 0 failed）