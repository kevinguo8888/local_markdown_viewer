#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
方案C：混合方案 - 监控桥接（最小可行接入 MVI）
说明：不移动 outputs 产物，通过相对路径导入监控部署器，受配置开关控制。
"""

import asyncio
import json
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "lad_integration.json"


def _load_config() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {"enabled": False, "monitoring": {"enabled": False}}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"enabled": False, "monitoring": {"enabled": False}}


async def start_monitoring_if_enabled() -> None:
    """在配置开启时启动监控部署器。"""
    cfg = _load_config()
    if not (cfg.get("enabled", False) and cfg.get("monitoring", {}).get("enabled", False)):
        return

    try:
        # 直接引用已迁入主项目目录的稳定模块
        from .monitoring_system_deployer import MonitoringSystemDeployer  # type: ignore
    except Exception:
        return

    deployer = MonitoringSystemDeployer()

    # 覆盖采样间隔与保留期（若配置提供）
    interval = cfg.get("monitoring", {}).get("interval_seconds")
    if isinstance(interval, (int, float)) and interval > 0:
        try:
            if "performance" in deployer.monitoring_config:
                deployer.monitoring_config["performance"]["interval"] = float(interval)
            if "error" in deployer.monitoring_config:
                deployer.monitoring_config["error"]["interval"] = max(1.0, float(interval))
            if "log" in deployer.monitoring_config:
                deployer.monitoring_config["log"]["interval"] = float(interval)
            if "system" in deployer.monitoring_config:
                deployer.monitoring_config["system"]["interval"] = max(10.0, float(interval))
        except Exception:
            pass

    # 覆盖存储路径到项目内 metrics 根目录
    try:
        metrics_dir = PROJECT_ROOT / "metrics"
        metrics_dir.mkdir(parents=True, exist_ok=True)
        # CI 断言需要 metrics/bridge 目录存在
        (metrics_dir / "bridge").mkdir(parents=True, exist_ok=True)
        if getattr(deployer, "storage_config", None) is None:
            deployer.storage_config = {}
        retention = cfg.get("monitoring", {}).get("retention_days", 7)
        try:
            retention = int(retention)
        except Exception:
            retention = 7
        deployer.storage_config.update({
            "metrics_file": metrics_dir / "metrics.json",
            "alerts_file": metrics_dir / "alerts.json",
            "reports_dir": metrics_dir / "reports",
            "retention_days": max(1, retention)
        })
        (metrics_dir / "reports").mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    try:
        await deployer.deploy_monitoring_system()
    except Exception:
        # 最小接入：静默失败，避免影响主程序启动
        return

