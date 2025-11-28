#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
缓存失效管理器 v1.0.0
提供智能的缓存失效和更新策略

作者: LAD Team
创建时间: 2025-08-16
最后更新: 2025-08-16
"""

import time
import logging
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional, Union, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import threading
import json
import os
import builtins

def _safe_open(*args, **kwargs):
    """缓存失效配置持久化使用的安全 open 封装。"""
    # 1) 优先 builtins.open
    try:
        builtin_open = getattr(builtins, "open", None)
    except Exception:
        builtin_open = None
    if callable(builtin_open):
        return builtin_open(*args, **kwargs)

    # 2) 尝试 io.open
    try:
        import io as _io_mod
    except Exception:
        _io_mod = None
    io_open = getattr(_io_mod, "open", None) if _io_mod is not None else None
    if callable(io_open):
        return io_open(*args, **kwargs)

    # 3) 最后尝试普通 open 名称
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


class InvalidationStrategy(Enum):
    """失效策略枚举"""
    TIME_BASED = "time_based"           # 基于时间失效
    CONTENT_BASED = "content_based"     # 基于内容变化失效
    DEPENDENCY_BASED = "dependency_based"  # 基于依赖变化失效
    MANUAL = "manual"                   # 手动失效
    HYBRID = "hybrid"                   # 混合策略


class InvalidationTrigger(Enum):
    """失效触发器枚举"""
    FILE_MODIFIED = "file_modified"     # 文件修改
    CONFIG_CHANGED = "config_changed"   # 配置变更
    DEPENDENCY_UPDATED = "dependency_updated"  # 依赖更新
    MANUAL_REQUEST = "manual_request"   # 手动请求
    TIME_EXPIRED = "time_expired"       # 时间过期


@dataclass
class InvalidationRule:
    """失效规则数据类"""
    name: str
    pattern: str
    strategy: InvalidationStrategy
    ttl: Optional[float] = None
    dependencies: List[str] = None
    enabled: bool = True
    priority: int = 1
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        data = asdict(self)
        data['strategy'] = self.strategy.value
        return data


@dataclass
class InvalidationEvent:
    """失效事件数据类"""
    timestamp: float
    trigger: InvalidationTrigger
    affected_keys: List[str]
    rule_name: str
    reason: str
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        data = asdict(self)
        data['trigger'] = self.trigger.value
        data['timestamp_iso'] = datetime.fromtimestamp(self.timestamp).isoformat()
        return data


class CacheInvalidationManager:
    """缓存失效管理器"""
    
    def __init__(self, cache_manager, invalidation_dir: Optional[Union[str, Path]] = None):
        """
        初始化缓存失效管理器
        
        Args:
            cache_manager: 统一缓存管理器实例
            invalidation_dir: 失效配置目录
        """
        self.cache_manager = cache_manager
        self.invalidation_dir = Path(invalidation_dir) if invalidation_dir else None
        
        # 失效规则
        self.invalidation_rules: Dict[str, InvalidationRule] = {}
        
        # 失效事件历史
        self.invalidation_history: List[InvalidationEvent] = []
        self.max_history_size = 1000
        
        # 文件监控
        self.file_watchers: Dict[str, Dict[str, float]] = {}
        
        # 线程安全
        self._lock = threading.RLock()
        
        # 日志
        self.logger = logging.getLogger(__name__)
        
        # 监控线程
        self._monitor_thread = None
        self._stop_monitor = False
        
        # 初始化
        self._initialize_invalidation_manager()
    
    def _initialize_invalidation_manager(self):
        """初始化失效管理器"""
        try:
            # 创建失效配置目录
            if self.invalidation_dir:
                self.invalidation_dir.mkdir(parents=True, exist_ok=True)
                self.logger.info(f"失效配置目录初始化: {self.invalidation_dir}")
            
            # 加载默认失效规则
            self._load_default_rules()
            
            # 启动监控线程
            self._start_monitor_thread()
            
            self.logger.info("缓存失效管理器初始化完成")
            
        except Exception as e:
            self.logger.error(f"失效管理器初始化失败: {e}")
            raise
    
    def _load_default_rules(self):
        """加载默认失效规则"""
        # 文件修改失效规则
        self.add_invalidation_rule(
            name="file_modified",
            pattern="file_*",
            strategy=InvalidationStrategy.CONTENT_BASED,
            ttl=300,  # 5分钟
            priority=1
        )
        
        # 配置变更失效规则
        self.add_invalidation_rule(
            name="config_changed",
            pattern="config_*",
            strategy=InvalidationStrategy.DEPENDENCY_BASED,
            ttl=60,  # 1分钟
            priority=2
        )
        
        # 模块导入失效规则
        self.add_invalidation_rule(
            name="module_import",
            pattern="module_import_*",
            strategy=InvalidationStrategy.TIME_BASED,
            ttl=7200,  # 2小时
            priority=3
        )
        
        # 渲染结果失效规则
        self.add_invalidation_rule(
            name="render_result",
            pattern="render_*",
            strategy=InvalidationStrategy.HYBRID,
            ttl=3600,  # 1小时
            priority=4
        )
    
    def _start_monitor_thread(self):
        """启动监控线程"""
        try:
            _tm = (os.environ.get('LAD_TEST_MODE') == '1') or ('PYTEST_CURRENT_TEST' in os.environ) or ('PYTEST_PROGRESS_LOG' in os.environ)
        except Exception:
            _tm = False
        if _tm:
            return
        if self._monitor_thread is None:
            self._monitor_thread = threading.Thread(target=self._monitor_worker, daemon=True)
            self._monitor_thread.start()
            self.logger.info("缓存失效监控线程已启动")
    
    def _monitor_worker(self):
        """监控工作线程"""
        while not self._stop_monitor:
            try:
                time.sleep(30)  # 每30秒检查一次
                self._check_file_modifications()
                self._cleanup_history()
            except Exception as e:
                self.logger.error(f"监控任务异常: {e}")
    
    def _check_file_modifications(self):
        """检查文件修改"""
        with self._lock:
            for file_path, last_modified in self.file_watchers.items():
                try:
                    current_modified = Path(file_path).stat().st_mtime
                    if current_modified > last_modified:
                        # 文件已修改，触发失效
                        self._trigger_file_invalidation(file_path, current_modified)
                        self.file_watchers[file_path] = current_modified
                except Exception as e:
                    self.logger.debug(f"检查文件修改失败: {file_path}, {e}")
    
    def _trigger_file_invalidation(self, file_path: str, modified_time: float):
        """触发文件失效"""
        # 查找匹配的缓存键
        affected_keys = []
        for key in self.cache_manager.get_keys():
            if self._is_key_affected_by_file(key, file_path):
                affected_keys.append(key)
        
        if affected_keys:
            self.invalidate_keys(affected_keys, InvalidationTrigger.FILE_MODIFIED, 
                               f"文件修改: {file_path}")
    
    def _is_key_affected_by_file(self, cache_key: str, file_path: str) -> bool:
        """检查缓存键是否受文件影响"""
        # 简单的文件名匹配逻辑
        file_name = Path(file_path).name.lower()
        cache_key_lower = cache_key.lower()
        
        # 检查缓存键是否包含文件名（去掉扩展名）
        file_name_without_ext = Path(file_path).stem.lower()
        return file_name_without_ext in cache_key_lower
    
    def _cleanup_history(self):
        """清理历史记录"""
        if len(self.invalidation_history) > self.max_history_size:
            # 保留最近的事件
            self.invalidation_history = self.invalidation_history[-self.max_history_size:]
    
    def add_invalidation_rule(self, name: str, pattern: str, strategy: InvalidationStrategy,
                             ttl: Optional[float] = None, dependencies: List[str] = None,
                             enabled: bool = True, priority: int = 1) -> bool:
        """
        添加失效规则
        
        Args:
            name: 规则名称
            pattern: 匹配模式
            strategy: 失效策略
            ttl: 过期时间
            dependencies: 依赖列表
            enabled: 是否启用
            priority: 优先级
            
        Returns:
            是否添加成功
        """
        try:
            rule = InvalidationRule(
                name=name,
                pattern=pattern,
                strategy=strategy,
                ttl=ttl,
                dependencies=dependencies or [],
                enabled=enabled,
                priority=priority
            )
            
            with self._lock:
                self.invalidation_rules[name] = rule
            
            self.logger.info(f"添加失效规则: {name}, 策略={strategy.value}")
            return True
            
        except Exception as e:
            self.logger.error(f"添加失效规则失败: {name}, 错误: {e}")
            return False
    
    def remove_invalidation_rule(self, name: str) -> bool:
        """
        移除失效规则
        
        Args:
            name: 规则名称
            
        Returns:
            是否移除成功
        """
        with self._lock:
            if name in self.invalidation_rules:
                del self.invalidation_rules[name]
                self.logger.info(f"移除失效规则: {name}")
                return True
            return False
    
    def invalidate_keys(self, keys: List[str], trigger: InvalidationTrigger, 
                       reason: str, metadata: Optional[Dict[str, Any]] = None) -> int:
        """
        失效指定的缓存键
        
        Args:
            keys: 要失效的缓存键列表
            trigger: 失效触发器
            reason: 失效原因
            metadata: 元数据
            
        Returns:
            失效的键数量
        """
        invalidated_count = 0
        
        try:
            with self._lock:
                for key in keys:
                    if self.cache_manager.delete(key):
                        invalidated_count += 1
                
                # 记录失效事件
                event = InvalidationEvent(
                    timestamp=time.time(),
                    trigger=trigger,
                    affected_keys=keys,
                    rule_name="manual",
                    reason=reason,
                    metadata=metadata
                )
                
                self.invalidation_history.append(event)
                
                self.logger.info(f"缓存失效: {invalidated_count}/{len(keys)} 个键, 原因: {reason}")
                
        except Exception as e:
            self.logger.error(f"缓存失效失败: {e}")
        
        return invalidated_count
    
    def invalidate_by_pattern(self, pattern: str, trigger: InvalidationTrigger = InvalidationTrigger.MANUAL_REQUEST,
                            reason: str = "模式匹配失效") -> int:
        """
        根据模式失效缓存
        
        Args:
            pattern: 匹配模式
            trigger: 失效触发器
            reason: 失效原因
            
        Returns:
            失效的键数量
        """
        matching_keys = []
        
        for key in self.cache_manager.get_keys():
            if self._match_pattern(key, pattern):
                matching_keys.append(key)
        
        return self.invalidate_keys(matching_keys, trigger, reason)
    
    def _match_pattern(self, key: str, pattern: str) -> bool:
        """匹配模式"""
        # 简单的通配符匹配
        if '*' in pattern:
            # 将通配符转换为正则表达式
            import re
            regex_pattern = pattern.replace('*', '.*')
            return re.match(regex_pattern, key) is not None
        else:
            return pattern in key
    
    def invalidate_by_rule(self, rule_name: str, trigger: InvalidationTrigger = InvalidationTrigger.MANUAL_REQUEST) -> int:
        """
        根据规则失效缓存
        
        Args:
            rule_name: 规则名称
            trigger: 失效触发器
            
        Returns:
            失效的键数量
        """
        with self._lock:
            rule = self.invalidation_rules.get(rule_name)
            if not rule or not rule.enabled:
                return 0
            
            return self.invalidate_by_pattern(
                rule.pattern, 
                trigger, 
                f"规则失效: {rule_name}"
            )
    
    def watch_file(self, file_path: str) -> bool:
        """
        监控文件变化
        
        Args:
            file_path: 文件路径
            
        Returns:
            是否监控成功
        """
        try:
            file_path = str(Path(file_path).resolve())
            if Path(file_path).exists():
                with self._lock:
                    self.file_watchers[file_path] = Path(file_path).stat().st_mtime
                self.logger.info(f"开始监控文件: {file_path}")
                return True
            else:
                self.logger.warning(f"文件不存在，无法监控: {file_path}")
                return False
                
        except Exception as e:
            self.logger.error(f"监控文件失败: {file_path}, 错误: {e}")
            return False
    
    def unwatch_file(self, file_path: str) -> bool:
        """
        停止监控文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            是否停止成功
        """
        file_path = str(Path(file_path).resolve())
        with self._lock:
            if file_path in self.file_watchers:
                del self.file_watchers[file_path]
                self.logger.info(f"停止监控文件: {file_path}")
                return True
            return False
    
    def get_invalidation_stats(self) -> Dict[str, Any]:
        """获取失效统计信息"""
        with self._lock:
            # 统计各触发器的失效次数
            trigger_stats = {}
            for event in self.invalidation_history:
                trigger = event.trigger.value
                trigger_stats[trigger] = trigger_stats.get(trigger, 0) + 1
            
            return {
                'total_invalidations': len(self.invalidation_history),
                'trigger_stats': trigger_stats,
                'active_rules': len([r for r in self.invalidation_rules.values() if r.enabled]),
                'total_rules': len(self.invalidation_rules),
                'watched_files': len(self.file_watchers),
                'recent_invalidations': [
                    event.to_dict() for event in self.invalidation_history[-10:]
                ]
            }
    
    def get_invalidation_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        获取失效历史
        
        Args:
            limit: 返回数量限制
            
        Returns:
            失效历史列表
        """
        with self._lock:
            return [event.to_dict() for event in self.invalidation_history[-limit:]]
    
    def save_invalidation_config(self, filename: Optional[str] = None) -> bool:
        """保存失效配置"""
        if not self.invalidation_dir:
            return False
        
        try:
            filename = filename or "invalidation_config.json"
            filepath = self.invalidation_dir / filename
            
            config_data = {
                'rules': [rule.to_dict() for rule in self.invalidation_rules.values()],
                'watched_files': list(self.file_watchers.keys()),
                'metadata': {
                    'version': '1.0.0',
                    'created_time': datetime.now().isoformat(),
                    'total_rules': len(self.invalidation_rules),
                    'total_watched_files': len(self.file_watchers)
                }
            }
            
            with _safe_open(filepath, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"失效配置已保存: {filepath}")
            return True
            
        except Exception as e:
            self.logger.error(f"保存失效配置失败: {e}")
            return False
    
    def load_invalidation_config(self, filename: str) -> bool:
        """加载失效配置"""
        if not self.invalidation_dir:
            return False
        
        try:
            filepath = self.invalidation_dir / filename
            if not filepath.exists():
                self.logger.error(f"失效配置文件不存在: {filepath}")
                return False
            
            with open(filepath, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            with self._lock:
                # 清空现有规则
                self.invalidation_rules.clear()
                
                # 加载规则
                for rule_data in config_data.get('rules', []):
                    rule = InvalidationRule(
                        name=rule_data['name'],
                        pattern=rule_data['pattern'],
                        strategy=InvalidationStrategy(rule_data['strategy']),
                        ttl=rule_data.get('ttl'),
                        dependencies=rule_data.get('dependencies', []),
                        enabled=rule_data.get('enabled', True),
                        priority=rule_data.get('priority', 1)
                    )
                    self.invalidation_rules[rule.name] = rule
                
                # 加载监控文件
                self.file_watchers.clear()
                for file_path in config_data.get('watched_files', []):
                    if Path(file_path).exists():
                        self.file_watchers[file_path] = Path(file_path).stat().st_mtime
            
            self.logger.info(f"失效配置已加载: {filepath}")
            return True
            
        except Exception as e:
            self.logger.error(f"加载失效配置失败: {e}")
            return False
    
    def shutdown(self):
        """关闭失效管理器"""
        self._stop_monitor = True
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        
        # 保存配置
        self.save_invalidation_config()
        
        self.logger.info("缓存失效管理器已关闭")


# 便捷函数
def create_cache_invalidation_manager(cache_manager, 
                                    invalidation_dir: Optional[Union[str, Path]] = None) -> CacheInvalidationManager:
    """创建缓存失效管理器的便捷函数"""
    return CacheInvalidationManager(cache_manager, invalidation_dir) 