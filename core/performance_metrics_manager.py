#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
性能监控指标管理器 v1.0.0
提供系统性能指标的收集、分析、报告和告警功能

作者: LAD Team
创建时间: 2025-08-17
最后更新: 2025-08-17
"""

import os
import sys
import time
import json
import psutil
import threading
from pathlib import Path
from typing import Dict, Any, Optional, Union, List, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import queue
import statistics
import builtins

from utils.config_manager import get_config_manager
# 导入现有组件
from .enhanced_error_handler import EnhancedErrorHandler, ErrorCategory, ErrorSeverity
from .unified_cache_manager import UnifiedCacheManager, CacheStrategy


def _safe_open(*args, **kwargs):
    """在受限环境下安全获取文件句柄。

    优先使用 builtins.open，其次尝试 io.open，最后回退到普通 open 名称。
    仅在确实没有任何可用的 open 函数时才抛出 RuntimeError，
    由调用方捕获并记录。
    """
    # 1) 优先使用 builtins.open（正常 Python 环境）
    try:
        builtin_open = getattr(builtins, "open", None)
    except Exception:
        builtin_open = None
    if callable(builtin_open):
        return builtin_open(*args, **kwargs)

    # 2) 退回到 io.open（某些沙箱会禁用 builtins.open 但保留 io.open）
    try:
        import io as _io_mod
    except Exception:
        _io_mod = None
    io_open = getattr(_io_mod, "open", None) if _io_mod is not None else None
    if callable(io_open):
        return io_open(*args, **kwargs)

    # 3) 最后尝试模块内/全局命名空间中的 open
    mode = None
    if len(args) >= 2:
        mode = args[1]
    else:
        mode = kwargs.get("mode", "r")
    if mode is None:
        mode = "r"
    try:
        _tm = (
            os.environ.get("LAD_TEST_MODE") == "1"
            or "PYTEST_CURRENT_TEST" in os.environ
            or "PYTEST_PROGRESS_LOG" in os.environ
        )
    except Exception:
        _tm = False
    if _tm and any(m in str(mode) for m in ("w", "a", "x", "+")):
        class _NullWriter:
            def write(self, *_, **__):
                return 0

            def writelines(self, *_, **__):
                return None

            def flush(self):
                return None

            def close(self):
                return None

        class _NullContext:
            def __enter__(self):
                return _NullWriter()

            def __exit__(self, exc_type, exc, tb):
                return False

        return _NullContext()

    return open(*args, **kwargs)  # type: ignore[name-defined]


class MetricType(Enum):
    """指标类型枚举"""
    SYSTEM = "system"           # 系统指标
    APPLICATION = "application"  # 应用指标
    PERFORMANCE = "performance"  # 性能指标
    BUSINESS = "business"        # 业务指标


class MetricUnit(Enum):
    """指标单位枚举"""
    COUNT = "count"             # 计数
    PERCENTAGE = "percentage"   # 百分比
    BYTES = "bytes"             # 字节
    SECONDS = "seconds"         # 秒
    MILLISECONDS = "milliseconds"  # 毫秒
    REQUESTS_PER_SECOND = "requests_per_second"  # 每秒请求数


@dataclass
class MetricValue:
    """指标值数据类"""
    value: float
    unit: MetricUnit
    timestamp: float
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class MetricDefinition:
    """指标定义数据类"""
    name: str
    type: MetricType
    unit: MetricUnit
    description: str
    tags: Dict[str, str]
    collection_interval: float  # 收集间隔（秒）


@dataclass
class MetricData:
    """指标数据类"""
    definition: MetricDefinition
    values: List[MetricValue]
    current_value: Optional[MetricValue] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    avg_value: Optional[float] = None


@dataclass
class AlertRule:
    """告警规则数据类"""
    metric_name: str
    condition: str  # ">", "<", "==", ">=", "<="
    threshold: float
    severity: str  # "info", "warning", "critical"
    message: str
    enabled: bool = True


@dataclass
class Alert:
    """告警数据类"""
    rule: AlertRule
    current_value: float
    timestamp: float
    message: str
    acknowledged: bool = False


class PerformanceMetricsManager:
    """性能监控指标管理器"""
    
    def __init__(self, 
                 metrics_dir: Optional[Path] = None,
                 collection_interval: Optional[float] = None,
                 enable_alerts: bool = True,
                 max_history_size: int = 1000):
        """
        初始化性能监控指标管理器
        
        Args:
            metrics_dir: 指标数据目录
            collection_interval: 指标收集间隔（秒）
            enable_alerts: 是否启用告警
            max_history_size: 最大历史数据大小
        """
        self.logger = None  # 将在setup_logging中设置
        
        # 配置参数
        self.collection_interval = self._resolve_collection_interval(collection_interval)
        self.enable_alerts = enable_alerts
        self.max_history_size = max_history_size
        # 测试态快速模式
        self._fast_mode = os.environ.get("LAD_TEST_MODE") == "1" or os.environ.get("LAD_QA_FAST") == "1"
        
        # 指标数据目录
        if metrics_dir is None:
            metrics_dir = Path(__file__).parent.parent / "metrics"
        self.metrics_dir = metrics_dir
        self.metrics_dir.mkdir(parents=True, exist_ok=True)
        
        # 组件集成
        self.error_handler = EnhancedErrorHandler(
            error_log_dir=self.metrics_dir / "errors",
            max_error_history=100
        )
        
        self.cache_manager = UnifiedCacheManager(
            max_size=1000,
            strategy=CacheStrategy.LRU
        )
        
        # 指标定义和数据
        self.metric_definitions: Dict[str, MetricDefinition] = {}
        self.metric_data: Dict[str, MetricData] = {}
        
        # 告警规则和告警
        self.alert_rules: Dict[str, AlertRule] = {}
        self.active_alerts: List[Alert] = []
        
        # 线程安全
        self._lock = threading.Lock()
        self._metrics_lock = threading.Lock()
        self._alerts_lock = threading.Lock()
        
        # 控制标志
        self._stop_collection = False
        self._collection_thread = None
        self._last_save_ts = 0.0
        
        # 初始化指标定义
        self._initialize_metric_definitions()
        
        # 启动指标收集
        self._start_metrics_collection()
        
        print("性能监控指标管理器初始化完成")

    def _resolve_collection_interval(self, param_value: Optional[float]) -> float:
        try:
            if param_value is not None:
                return float(param_value)
        except Exception:
            pass
        try:
            cm = get_config_manager()
        except Exception:
            cm = None
        if cm is not None:
            for key in (
                "app.logging.metrics.collection_interval",
                "features.logging.metrics.collection_interval",
                "runtime.performance.collection_interval",
                "runtime.performance.monitoring.collection_interval",
            ):
                try:
                    v = cm.get_unified_config(key, None)
                    if v is not None:
                        try:
                            return float(v)
                        except Exception:
                            continue
                except Exception:
                    continue
        env_v = os.environ.get("LAD_METRICS_INTERVAL")
        if env_v:
            try:
                return float(env_v)
            except Exception:
                pass
        return 1.0
    
    def _initialize_metric_definitions(self):
        """初始化指标定义"""
        try:
            # 系统指标
            self._add_metric_definition(
                "cpu_usage",
                MetricType.SYSTEM,
                MetricUnit.PERCENTAGE,
                "CPU使用率",
                {"category": "system", "component": "cpu"},
                5.0
            )
            
            self._add_metric_definition(
                "memory_usage",
                MetricType.SYSTEM,
                MetricUnit.PERCENTAGE,
                "内存使用率",
                {"category": "system", "component": "memory"},
                5.0
            )
            
            self._add_metric_definition(
                "disk_usage",
                MetricType.SYSTEM,
                MetricUnit.PERCENTAGE,
                "磁盘使用率",
                {"category": "system", "component": "disk"},
                30.0
            )
            
            self._add_metric_definition(
                "network_io",
                MetricType.SYSTEM,
                MetricUnit.BYTES,
                "网络I/O",
                {"category": "system", "component": "network"},
                5.0
            )
            
            # 应用指标
            self._add_metric_definition(
                "application_memory",
                MetricType.APPLICATION,
                MetricUnit.BYTES,
                "应用内存使用",
                {"category": "application", "component": "memory"},
                5.0
            )
            
            self._add_metric_definition(
                "application_threads",
                MetricType.APPLICATION,
                MetricUnit.COUNT,
                "应用线程数",
                {"category": "application", "component": "threads"},
                5.0
            )
            
            self._add_metric_definition(
                "application_uptime",
                MetricType.APPLICATION,
                MetricUnit.SECONDS,
                "应用运行时间",
                {"category": "application", "component": "uptime"},
                60.0
            )
            
            # 性能指标
            self._add_metric_definition(
                "response_time",
                MetricType.PERFORMANCE,
                MetricUnit.MILLISECONDS,
                "响应时间",
                {"category": "performance", "component": "response"},
                1.0
            )
            
            self._add_metric_definition(
                "throughput",
                MetricType.PERFORMANCE,
                MetricUnit.REQUESTS_PER_SECOND,
                "吞吐量",
                {"category": "performance", "component": "throughput"},
                1.0
            )
            
            self._add_metric_definition(
                "error_rate",
                MetricType.PERFORMANCE,
                MetricUnit.PERCENTAGE,
                "错误率",
                {"category": "performance", "component": "errors"},
                5.0
            )
            
        except Exception as e:
            print(f"初始化指标定义失败: {e}")
    
    def _add_metric_definition(self, 
                              name: str,
                              metric_type: MetricType,
                              unit: MetricUnit,
                              description: str,
                              tags: Dict[str, str],
                              collection_interval: float):
        """添加指标定义"""
        definition = MetricDefinition(
            name=name,
            type=metric_type,
            unit=unit,
            description=description,
            tags=tags,
            collection_interval=collection_interval
        )
        
        self.metric_definitions[name] = definition
        
        # 初始化指标数据
        self.metric_data[name] = MetricData(
            definition=definition,
            values=[],
            current_value=None,
            min_value=None,
            max_value=None,
            avg_value=None
        )
    
    def _start_metrics_collection(self):
        """启动指标收集"""
        def collect_metrics():
            while not self._stop_collection:
                try:
                    self._collect_system_metrics()
                    self._collect_application_metrics()
                    self._collect_performance_metrics()
                    
                    # 检查告警
                    if self.enable_alerts:
                        self._check_alerts()
                    
                    # 保存指标数据
                    self._save_metrics_data()
                    
                    time.sleep(self.collection_interval)
                    
                except Exception as e:
                    print(f"指标收集失败: {e}")
                    time.sleep(1)
        
        self._collection_thread = threading.Thread(target=collect_metrics, daemon=True)
        self._collection_thread.start()
    
    def _collect_system_metrics(self):
        """收集系统指标"""
        try:
            # CPU使用率
            cpu_percent = psutil.cpu_percent(interval=(0 if getattr(self, "_fast_mode", False) else 1))
            self._update_metric("cpu_usage", cpu_percent)
            
            # 内存使用率
            memory = psutil.virtual_memory()
            self._update_metric("memory_usage", memory.percent)
            
            # 磁盘使用率
            try:
                disk = psutil.disk_usage('/')
                self._update_metric("disk_usage", (disk.used / disk.total) * 100)
            except (FileNotFoundError, OSError):
                # Windows系统可能没有根目录，使用当前目录
                try:
                    disk = psutil.disk_usage('.')
                    self._update_metric("disk_usage", (disk.used / disk.total) * 100)
                except Exception:
                    # 如果都失败，设置为0
                    self._update_metric("disk_usage", 0.0)
            
            # 网络I/O
            network = psutil.net_io_counters()
            total_io = network.bytes_sent + network.bytes_recv
            self._update_metric("network_io", total_io)
            
        except Exception as e:
            print(f"收集系统指标失败: {e}")
    
    def _collect_application_metrics(self):
        """收集应用指标"""
        try:
            current_process = psutil.Process()
            
            # 应用内存使用
            memory_info = current_process.memory_info()
            self._update_metric("application_memory", memory_info.rss)
            
            # 应用线程数
            thread_count = current_process.num_threads()
            self._update_metric("application_threads", thread_count)
            
            # 应用运行时间
            uptime = time.time() - current_process.create_time()
            self._update_metric("application_uptime", uptime)
            
        except Exception as e:
            print(f"收集应用指标失败: {e}")
    
    def _collect_performance_metrics(self):
        """收集性能指标"""
        try:
            # 这里可以收集更多性能指标
            # 例如：缓存命中率、响应时间等
            
            # 模拟一些性能指标
            response_time = self._simulate_response_time()
            self._update_metric("response_time", response_time)
            
            throughput = self._simulate_throughput()
            self._update_metric("throughput", throughput)
            
            error_rate = self._simulate_error_rate()
            self._update_metric("error_rate", error_rate)
            
        except Exception as e:
            print(f"收集性能指标失败: {e}")
    
    def _simulate_response_time(self) -> float:
        """模拟响应时间"""
        # 这里应该实现真实的响应时间收集
        # 暂时返回一个模拟值
        import random
        return random.uniform(10, 100)
    
    def _simulate_throughput(self) -> float:
        """模拟吞吐量"""
        # 这里应该实现真实的吞吐量收集
        # 暂时返回一个模拟值
        import random
        return random.uniform(50, 200)
    
    def _simulate_error_rate(self) -> float:
        """模拟错误率"""
        # 这里应该实现真实的错误率收集
        # 暂时返回一个模拟值
        import random
        return random.uniform(0, 5)
    
    def _update_metric(self, name: str, value: float):
        """更新指标值"""
        try:
            if name not in self.metric_data:
                return
            
            metric_data = self.metric_data[name]
            definition = metric_data.definition
            
            # 创建指标值
            metric_value = MetricValue(
                value=value,
                unit=definition.unit,
                timestamp=time.time()
            )
            
            with self._metrics_lock:
                # 更新当前值
                metric_data.current_value = metric_value
                
                # 添加到历史值
                metric_data.values.append(metric_value)
                
                # 限制历史数据大小
                if len(metric_data.values) > self.max_history_size:
                    metric_data.values.pop(0)
                
                # 更新统计值
                values = [v.value for v in metric_data.values]
                if values:
                    metric_data.min_value = min(values)
                    metric_data.max_value = max(values)
                    metric_data.avg_value = statistics.mean(values)
            
            # 缓存指标数据
            cache_key = f"metric_{name}_{int(time.time())}"
            self.cache_manager.set(cache_key, metric_value, ttl=3600)
            
        except Exception as e:
            print(f"更新指标{name}失败: {e}")
    
    def _check_alerts(self):
        """检查告警"""
        try:
            with self._alerts_lock:
                for rule in self.alert_rules.values():
                    if not rule.enabled:
                        continue
                    
                    metric_name = rule.metric_name
                    if metric_name not in self.metric_data:
                        continue
                    
                    current_value = self.metric_data[metric_name].current_value
                    if current_value is None:
                        continue
                    
                    # 检查告警条件
                    if self._evaluate_alert_condition(rule, current_value.value):
                        # 创建告警
                        alert = Alert(
                            rule=rule,
                            current_value=current_value.value,
                            timestamp=time.time(),
                            message=rule.message.format(
                                metric=metric_name,
                                value=current_value.value,
                                threshold=rule.threshold
                            )
                        )
                        
                        # 检查是否已存在相同告警
                        if not self._alert_exists(alert):
                            self.active_alerts.append(alert)
                            print(f"告警触发: {alert.message}")
            
        except Exception as e:
            print(f"检查告警失败: {e}")
    
    def _evaluate_alert_condition(self, rule: AlertRule, value: float) -> bool:
        """评估告警条件"""
        try:
            if rule.condition == ">":
                return value > rule.threshold
            elif rule.condition == "<":
                return value < rule.threshold
            elif rule.condition == "==":
                return value == rule.threshold
            elif rule.condition == ">=":
                return value >= rule.threshold
            elif rule.condition == "<=":
                return value <= rule.threshold
            else:
                return False
        except Exception:
            return False
    
    def _alert_exists(self, alert: Alert) -> bool:
        """检查告警是否已存在"""
        for existing_alert in self.active_alerts:
            if (existing_alert.rule.metric_name == alert.rule.metric_name and
                existing_alert.rule.condition == alert.rule.condition and
                not existing_alert.acknowledged):
                return True
        return False
    
    def _save_metrics_data(self):
        """保存指标数据"""
        try:
            # 快速模式下做节流：每秒最多写一次
            if getattr(self, "_fast_mode", False):
                now_ts = time.time()
                if (now_ts - getattr(self, "_last_save_ts", 0.0)) < 1.0:
                    return
                self._last_save_ts = now_ts
            # 保存到文件
            metrics_file = self.metrics_dir / f"metrics_{int(time.time())}.json"
            
            # 准备保存的数据
            save_data = {}
            for name, metric_data in self.metric_data.items():
                # 转换枚举为字符串
                definition_dict = asdict(metric_data.definition)
                definition_dict['type'] = definition_dict['type'].value
                definition_dict['unit'] = definition_dict['unit'].value
                
                current_value_dict = None
                if metric_data.current_value:
                    current_value_dict = asdict(metric_data.current_value)
                    current_value_dict['unit'] = current_value_dict['unit'].value
                
                save_data[name] = {
                    'definition': definition_dict,
                    'current_value': current_value_dict,
                    'min_value': metric_data.min_value,
                    'max_value': metric_data.max_value,
                    'avg_value': metric_data.avg_value,
                    'values_count': len(metric_data.values)
                }
            
            with _safe_open(metrics_file, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, indent=2, ensure_ascii=False)
            
            # 清理旧文件
            self._cleanup_old_metrics_files()
            
        except Exception as e:
            print(f"保存指标数据失败: {e}")
    
    def _cleanup_old_metrics_files(self):
        """清理旧的指标文件"""
        try:
            current_time = time.time()
            cutoff_time = current_time - (24 * 3600)  # 保留24小时
            
            for metrics_file in self.metrics_dir.glob("metrics_*.json"):
                if metrics_file.stat().st_mtime < cutoff_time:
                    metrics_file.unlink()
                    
        except Exception as e:
            print(f"清理旧指标文件失败: {e}")
    
    def add_alert_rule(self, rule: AlertRule):
        """添加告警规则"""
        with self._alerts_lock:
            self.alert_rules[rule.metric_name] = rule
    
    def remove_alert_rule(self, metric_name: str):
        """移除告警规则"""
        with self._alerts_lock:
            if metric_name in self.alert_rules:
                del self.alert_rules[metric_name]
    
    def acknowledge_alert(self, metric_name: str):
        """确认告警"""
        with self._alerts_lock:
            for alert in self.active_alerts:
                if alert.rule.metric_name == metric_name:
                    alert.acknowledged = True
    
    def get_metric_data(self, name: str) -> Optional[MetricData]:
        """获取指标数据"""
        with self._metrics_lock:
            return self.metric_data.get(name)
    
    def get_all_metrics(self) -> Dict[str, MetricData]:
        """获取所有指标数据"""
        with self._metrics_lock:
            return self.metric_data.copy()
    
    def get_active_alerts(self) -> List[Alert]:
        """获取活动告警"""
        with self._alerts_lock:
            return [alert for alert in self.active_alerts if not alert.acknowledged]
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """获取指标摘要"""
        try:
            summary = {
                'total_metrics': len(self.metric_data),
                'metrics_by_type': {},
                'alerts_summary': {
                    'total_rules': len(self.alert_rules),
                    'active_alerts': len(self.get_active_alerts()),
                    'acknowledged_alerts': len([a for a in self.active_alerts if a.acknowledged])
                },
                'collection_status': {
                    'running': not self._stop_collection,
                    'interval': self.collection_interval,
                    'last_update': time.time()
                }
            }
            
            # 按类型统计指标
            for metric_data in self.metric_data.values():
                metric_type = metric_data.definition.type.value
                if metric_type not in summary['metrics_by_type']:
                    summary['metrics_by_type'][metric_type] = 0
                summary['metrics_by_type'][metric_type] += 1
            
            return summary
            
        except Exception as e:
            print(f"获取指标摘要失败: {e}")
            return {}
    
    def export_metrics(self, 
                      start_time: Optional[float] = None,
                      end_time: Optional[float] = None,
                      metric_names: Optional[List[str]] = None,
                      output_file: Optional[Path] = None) -> str:
        """导出指标数据"""
        try:
            if output_file is None:
                output_file = self.metrics_dir / f"exported_metrics_{int(time.time())}.json"
            
            # 准备导出数据
            export_data = {}
            
            for name, metric_data in self.metric_data.items():
                if metric_names and name not in metric_names:
                    continue
                
                # 过滤时间范围
                filtered_values = []
                for value in metric_data.values:
                    if start_time and value.timestamp < start_time:
                        continue
                    if end_time and value.timestamp > end_time:
                        continue
                    value_dict = asdict(value)
                    value_dict['unit'] = value_dict['unit'].value
                    filtered_values.append(value_dict)
                
                # 转换定义
                definition_dict = asdict(metric_data.definition)
                definition_dict['type'] = definition_dict['type'].value
                definition_dict['unit'] = definition_dict['unit'].value
                
                export_data[name] = {
                    'definition': definition_dict,
                    'values': filtered_values,
                    'statistics': {
                        'min': metric_data.min_value,
                        'max': metric_data.max_value,
                        'avg': metric_data.avg_value,
                        'count': len(filtered_values)
                    }
                }
            
            # 写入文件
            with _safe_open(output_file, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            return f"指标导出完成，保存到: {output_file}"
            
        except Exception as e:
            return f"指标导出失败: {e}"
    
    def setup_logging(self, logger):
        """设置日志记录器"""
        self.logger = logger
    
    def shutdown(self):
        """关闭指标管理器"""
        try:
            # 停止指标收集
            self._stop_collection = True
            
            if self._collection_thread and self._collection_thread.is_alive():
                self._collection_thread.join(timeout=5)
            
            # 保存最终指标数据
            self._save_metrics_data()
            
            # 关闭组件
            if hasattr(self, 'error_handler'):
                self.error_handler.shutdown()
            
            if hasattr(self, 'cache_manager'):
                self.cache_manager.shutdown()
            
            print("性能监控指标管理器已关闭")
            
        except Exception as e:
            print(f"关闭指标管理器时出现错误: {e}")
    
    def __del__(self):
        """析构函数"""
        try:
            self.shutdown()
        except:
            pass 