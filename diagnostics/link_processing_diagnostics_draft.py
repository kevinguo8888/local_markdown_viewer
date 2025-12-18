"""LAD-IMPL-015: 链接处理自动化诊断入口（规划草案版）

本模块仅作为 015 诊断任务的**最小脚本骨架**：
- 当前版本只输出“诊断计划”摘要，不执行任何真实诊断；
- 不依赖 psutil、PyQt 等重型组件，避免给现有环境增加负担；
- 为未来实现预留函数与数据结构挂载点。

参考文档：
- docs/LAD-IMPL-015-自动化诊断-任务提示词.md
- docs/015-诊断方案.md
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List, Optional


def build_plan_summary() -> Dict[str, Any]:
    """构建一份关于 015 链接处理诊断的计划摘要（草案）。

    当前实现：
    - 仅返回静态结构化信息；
    - 不访问文件系统，不读取配置；
    - 目的是为未来实现提供统一的“计划视图”入口。
    """

    return {
        "version": "0.1-draft",
        "status": "planning_only",
        "docs": [
            "docs/LAD-IMPL-015-自动化诊断-任务提示词.md",
            "docs/015-诊断方案.md",
        ],
        "stages": [
            {
                "id": "plan",
                "title": "规划视图",
                "description": "输出诊断范围、阶段与相关文档的结构化描述，仅用于规划。",
            },
            {
                "id": "preflight",
                "title": "前置条件自检（预留）",
                "description": "未来用于检查配置与依赖是否满足运行诊断的最小要求。当前仓库中未实现。",
            },
            {
                "id": "link_context",
                "title": "链接处理上下文聚合（预留）",
                "description": "未来用于收集链接处理配置、测试结果与日志摘要。当前仓库中未实现。",
            },
            {
                "id": "link_diagnostics",
                "title": "链接处理诊断执行（预留）",
                "description": "未来用于运行链接处理相关的自动化诊断规则。当前仓库中未实现。",
            },
            {
                "id": "report",
                "title": "诊断报告生成（预留）",
                "description": "未来用于生成机器可读的 JSON 报告与人可读摘要。当前仓库中未实现。",
            },
        ],
        "notes": [
            "本脚本当前仅输出规划信息，不执行任何真实诊断。",
            "未来实现可在保持命令行参数兼容的前提下，逐步填充各阶段逻辑。",
        ],
    }


def run_preflight_checks() -> Dict[str, Any]:
    """015 前置条件检查占位实现。

    说明：
    - 未来可在此处实现对配置文件、模块依赖等的实际检查；
    - 本仓库阶段返回占位结果，明确提示“未实装”。
    """

    return {
        "status": "draft_only",
        "message": "Preflight checks are not implemented in this repository.",
        "checks": [],
    }


def run_link_processing_diagnostics() -> Dict[str, Any]:
    """链接处理诊断占位实现。

    说明：
    - 未来可在此处调用 DebugDiagnosticsManager 或自定义诊断逻辑；
    - 本仓库阶段返回占位结果，明确提示“未实装”。
    """

    return {
        "status": "draft_only",
        "message": "Link processing diagnostics are not implemented in this repository.",
        "items": [],
    }


def main(argv: Optional[List[str]] = None) -> int:
    """命令行入口（规划草案版）。

    当前行为：
    - 默认与 `--plan-only` 等价，仅输出规划信息；
    - 不执行任何真实诊断，不访问外部系统；
    - 退出码为 0，表示脚本自身运行成功。
    """

    parser = argparse.ArgumentParser(
        description=(
            "LAD-IMPL-015 链接处理自动化诊断入口（规划草案版）："
            "当前仅输出诊断计划，不执行真实诊断。"
        )
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="仅输出诊断计划（当前行为与默认一致）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="与 --plan-only 等价，预留向后兼容开关",
    )

    args = parser.parse_args(argv)

    plan = build_plan_summary()

    # 未来可以根据参数决定是否实际执行 preflight / link_diagnostics 等逻辑。
    # 在本仓库中，无论是否传入参数，都只输出计划信息。
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    print(
        "\nNOTE: Diagnostics execution is not implemented in this repository. "
        "This script only prints the planning draft."
    )

    return 0


if __name__ == "__main__":  # pragma: no cover - 入口包装
    raise SystemExit(main())
