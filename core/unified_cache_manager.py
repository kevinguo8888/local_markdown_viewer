#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一缓存管理器 v1.0.0
提供统一的缓存管理接口，支持多种缓存策略和失效机制

作者: LAD Team
创建时间: 2025-08-16
最后更新: 2025-08-16
"""

import json
import time
import hashlib
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional, Union, List, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
from collections import OrderedDict
import threading
import weakref
import builtins


def _safe_open(*args, **kwargs):
    """统一缓存管理器的安全 open 封装。"""
    # 1) builtins.open
    try:
        builtin_open = getattr(builtins, "open", None)
    except Exception:
        builtin_open = None
    if callable(builtin_open):
        return builtin_open(*args, **kwargs)

    # 2) io.open
    try:
        import io as _io_mod
    except Exception:
        _io_mod = None
    io_open = getattr(_io_mod, "open", None) if _io_mod is not None else None
    if callable(io_open):
        return io_open(*args, **kwargs)

    # 3) 普通 open 名称
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


class CacheStrategy(Enum):
    """缓存策略枚举"""
    LRU = "lru"           # 最近最少使用
    LFU = "lfu"           # 最少使用频率
    FIFO = "fifo"         # 先进先出
    TTL = "ttl"           # 基于时间过期
    HYBRID = "hybrid"     # 混合策略


class CacheStatus(Enum):
    """缓存状态枚举"""
    VALID = "valid"       # 有效
    EXPIRED = "expired"   # 已过期
    INVALID = "invalid"   # 无效
    PENDING = "pending"   # 待更新


@dataclass
class CacheEntry:
    """缓存条目数据类"""
    key: str
    value: Any
    created_time: float
    last_access_time: float
    access_count: int
    ttl: Optional[float] = None
    strategy: CacheStrategy = CacheStrategy.LRU
    metadata: Optional[Dict[str, Any]] = None
    
    def is_expired(self) -> bool:
        """检查是否过期"""
        if self.ttl is None:
            return False
        return time.time() - self.created_time > self.ttl
    
    def update_access(self):
        """更新访问信息"""
        self.last_access_time = time.time()
        self.access_count += 1
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        data = asdict(self)
        data['strategy'] = self.strategy.value
        if data.get('metadata') is not None:
            data['metadata'] = dict(data['metadata'])
        return data


@dataclass
class CacheStats:
    """缓存统计信息数据类"""
    total_entries: int
    hit_count: int
    miss_count: int
    eviction_count: int
    total_size: int
    max_size: int
    hit_rate: float
    memory_usage: float
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return asdict(self)


class UnifiedCacheManager:
    """统一缓存管理器"""
    
    def __init__(self, max_size: int = 1000, default_ttl: Optional[float] = None,
                 strategy: CacheStrategy = CacheStrategy.LRU, cache_dir: Optional[Union[str, Path]] = None):
        """
        初始化统一缓存管理器
        
        Args:
            max_size: 最大缓存条目数
            default_ttl: 默认过期时间（秒）
            strategy: 缓存策略
            cache_dir: 缓存目录（用于持久化）
        """
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.strategy = strategy
        self.cache_dir = Path(cache_dir) if cache_dir else None
        
        # 缓存存储
        self._cache: Dict[str, CacheEntry] = OrderedDict()
        
        # 统计信息
        self._stats = CacheStats(
            total_entries=0,
            hit_count=0,
            miss_count=0,
            eviction_count=0,
            total_size=0,
            max_size=max_size,
            hit_rate=0.0,
            memory_usage=0.0
        )
        
        # 线程安全
        self._lock = threading.RLock()
        
        # 日志
        self.logger = logging.getLogger(__name__)
        
        # 清理任务
        self._cleanup_thread = None
        self._stop_cleanup = False
        
        # 初始化
        self._initialize_cache()
    
    def _initialize_cache(self):
        """初始化缓存"""
        try:
            # 创建缓存目录
            if self.cache_dir:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                self.logger.info(f"缓存目录初始化: {self.cache_dir}")
            
            # 启动清理任务
            self._start_cleanup_task()
            
            self.logger.info(f"统一缓存管理器初始化完成: 策略={self.strategy.value}, 最大大小={self.max_size}")
            
        except Exception as e:
            self.logger.error(f"缓存初始化失败: {e}")
            raise
    
    def _start_cleanup_task(self):
        """启动清理任务"""
        try:
            _tm = (os.environ.get('LAD_TEST_MODE') == '1') or ('PYTEST_CURRENT_TEST' in os.environ) or ('PYTEST_PROGRESS_LOG' in os.environ)
        except Exception:
            _tm = False
        if _tm:
            return
        if self._cleanup_thread is None:
            self._cleanup_thread = threading.Thread(target=self._cleanup_worker, daemon=True)
            self._cleanup_thread.start()
            self.logger.info("缓存清理任务已启动")
    
    def _cleanup_worker(self):
        """清理工作线程"""
        while not self._stop_cleanup:
            try:
                time.sleep(60)  # 每分钟清理一次
                self._cleanup_expired_entries()
            except Exception as e:
                self.logger.error(f"清理任务异常: {e}")
    
    def _cleanup_expired_entries(self):
        """清理过期条目"""
        with self._lock:
            expired_keys = []
            for key, entry in self._cache.items():
                if entry.is_expired():
                    expired_keys.append(key)
            
            for key in expired_keys:
                self._remove_entry(key)
                self.logger.debug(f"清理过期缓存: {key}")
    
    def _remove_entry(self, key: str):
        """移除缓存条目"""
        if key in self._cache:
            entry = self._cache.pop(key)
            self._stats.total_entries -= 1
            self._stats.eviction_count += 1
            self._update_stats()
    
    def _update_stats(self):
        """更新统计信息"""
        total_requests = self._stats.hit_count + self._stats.miss_count
        if total_requests > 0:
            self._stats.hit_rate = self._stats.hit_count / total_requests
        
        self._stats.total_size = len(self._cache)
        self._stats.memory_usage = self._estimate_memory_usage()
    
    def _estimate_memory_usage(self) -> float:
        """估算内存使用量（MB）"""
        try:
            total_size = 0
            for entry in self._cache.values():
                # 估算每个条目的大小
                key_size = len(entry.key.encode('utf-8'))
                value_size = len(str(entry.value).encode('utf-8'))
                metadata_size = len(str(entry.metadata or {}).encode('utf-8'))
                total_size += key_size + value_size + metadata_size + 100  # 额外开销
            
            return total_size / (1024 * 1024)  # 转换为MB
        except Exception:
            return 0.0
    
    def _generate_key(self, *args, **kwargs) -> str:
        """生成缓存键"""
        key_data = {
            'args': args,
            'kwargs': sorted(kwargs.items())
        }
        key_str = json.dumps(key_data, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(key_str.encode('utf-8')).hexdigest()
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取缓存值
        
        Args:
            key: 缓存键
            default: 默认值
            
        Returns:
            缓存值或默认值
        """
        with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                
                # 检查是否过期
                if entry.is_expired():
                    self._remove_entry(key)
                    self._stats.miss_count += 1
                    self.logger.debug(f"缓存过期: {key}")
                    return default
                
                # 更新访问信息
                entry.update_access()
                
                # 根据策略调整位置
                if self.strategy == CacheStrategy.LRU:
                    self._cache.move_to_end(key)
                
                self._stats.hit_count += 1
                self._update_stats()
                
                self.logger.debug(f"缓存命中: {key}")
                return entry.value
            else:
                self._stats.miss_count += 1
                self._update_stats()
                self.logger.debug(f"缓存未命中: {key}")
                return default
    
    def set(self, key: str, value: Any, ttl: Optional[float] = None, 
            metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        设置缓存值
        
        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒）
            metadata: 元数据
            
        Returns:
            是否设置成功
        """
        try:
            with self._lock:
                # 检查是否需要清理空间
                if len(self._cache) >= self.max_size:
                    self._evict_entries()
                
                # 创建缓存条目
                entry = CacheEntry(
                    key=key,
                    value=value,
                    created_time=time.time(),
                    last_access_time=time.time(),
                    access_count=1,
                    ttl=ttl or self.default_ttl,
                    strategy=self.strategy,
                    metadata=metadata or {}
                )
                
                # 添加到缓存
                self._cache[key] = entry
                self._stats.total_entries += 1
                self._update_stats()
                
                self.logger.debug(f"缓存设置: {key}")
                return True
                
        except Exception as e:
            self.logger.error(f"设置缓存失败: {key}, 错误: {e}")
            return False
    
    def _evict_entries(self):
        """驱逐缓存条目"""
        if not self._cache:
            return
        
        if self.strategy == CacheStrategy.LRU:
            # 移除最久未使用的条目
            oldest_key = next(iter(self._cache))
            self._remove_entry(oldest_key)
            
        elif self.strategy == CacheStrategy.LFU:
            # 移除使用频率最低的条目
            least_frequent_key = min(self._cache.keys(), 
                                   key=lambda k: self._cache[k].access_count)
            self._remove_entry(least_frequent_key)
            
        elif self.strategy == CacheStrategy.FIFO:
            # 移除最先添加的条目
            first_key = next(iter(self._cache))
            self._remove_entry(first_key)
            
        elif self.strategy == CacheStrategy.TTL:
            # 移除最早过期的条目
            earliest_expiry_key = min(self._cache.keys(),
                                    key=lambda k: self._cache[k].created_time + (self._cache[k].ttl or 0))
            self._remove_entry(earliest_expiry_key)
            
        elif self.strategy == CacheStrategy.HYBRID:
            # 混合策略：优先移除过期条目，然后按LRU移除
            expired_keys = [k for k, v in self._cache.items() if v.is_expired()]
            if expired_keys:
                self._remove_entry(expired_keys[0])
            else:
                oldest_key = next(iter(self._cache))
                self._remove_entry(oldest_key)
    
    def delete(self, key: str) -> bool:
        """
        删除缓存条目
        
        Args:
            key: 缓存键
            
        Returns:
            是否删除成功
        """
        with self._lock:
            if key in self._cache:
                self._remove_entry(key)
                self.logger.debug(f"缓存删除: {key}")
                return True
            return False
    
    def clear(self):
        """清空所有缓存"""
        with self._lock:
            self._cache.clear()
            self._stats.total_entries = 0
            self._stats.eviction_count += len(self._cache)
            self._update_stats()
            self.logger.info("缓存已清空")
    
    def exists(self, key: str) -> bool:
        """
        检查缓存键是否存在
        
        Args:
            key: 缓存键
            
        Returns:
            是否存在
        """
        with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                if entry.is_expired():
                    self._remove_entry(key)
                    return False
                return True
            return False
    
    def get_stats(self) -> CacheStats:
        """获取缓存统计信息"""
        with self._lock:
            self._update_stats()
            return CacheStats(
                total_entries=self._stats.total_entries,
                hit_count=self._stats.hit_count,
                miss_count=self._stats.miss_count,
                eviction_count=self._stats.eviction_count,
                total_size=self._stats.total_size,
                max_size=self._stats.max_size,
                hit_rate=self._stats.hit_rate,
                memory_usage=self._stats.memory_usage
            )
    
    def get_keys(self) -> List[str]:
        """获取所有缓存键"""
        with self._lock:
            return list(self._cache.keys())
    
    def iter_keys(self):
        """惰性迭代缓存键，供大规模遍历使用。"""
        with self._lock:
            for key in list(self._cache.keys()):
                yield key

    def get_entry_info(self, key: str) -> Optional[Dict[str, Any]]:
        """获取缓存条目信息"""
        with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                return {
                    'key': entry.key,
                    'created_time': datetime.fromtimestamp(entry.created_time).isoformat(),
                    'last_access_time': datetime.fromtimestamp(entry.last_access_time).isoformat(),
                    'access_count': entry.access_count,
                    'ttl': entry.ttl,
                    'is_expired': entry.is_expired(),
                    'strategy': entry.strategy.value,
                    'metadata': entry.metadata
                }
            return None
    
    def set_strategy(self, strategy: CacheStrategy):
        """设置缓存策略"""
        with self._lock:
            self.strategy = strategy
            # 更新所有条目的策略
            for entry in self._cache.values():
                entry.strategy = strategy
            self.logger.info(f"缓存策略已更新: {strategy.value}")
    
    def set_max_size(self, max_size: int):
        """设置最大缓存大小"""
        with self._lock:
            self.max_size = max_size
            self._stats.max_size = max_size
            # 如果当前大小超过新的最大大小，进行清理
            while len(self._cache) > max_size:
                self._evict_entries()
            self.logger.info(f"最大缓存大小已更新: {max_size}")
    
    def save_to_disk(self, filename: Optional[str] = None) -> bool:
        """保存缓存到磁盘"""
        if not self.cache_dir:
            self.logger.warning("未设置缓存目录，无法保存到磁盘")
            return False
        
        try:
            filename = filename or f"cache_backup_{int(time.time())}.json"
            filepath = self.cache_dir / filename
            
            with self._lock:
                cache_data = {
                    'metadata': {
                        'version': '1.0.0',
                        'created_time': datetime.now().isoformat(),
                        'strategy': self.strategy.value,
                        'max_size': self.max_size,
                        'stats': self._stats.to_dict()
                    },
                    'entries': {}
                }
                
                for key, entry in self._cache.items():
                    if not entry.is_expired():
                        payload = entry.to_dict()
                        try:
                            json.dumps(payload['value'])
                        except TypeError:
                            payload['value'] = repr(payload['value'])
                            payload.setdefault('metadata', {})['serialized'] = False
                        else:
                            payload.setdefault('metadata', {})['serialized'] = True
                        cache_data['entries'][key] = payload
                
                with _safe_open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(cache_data, f, indent=2, ensure_ascii=False)
                
                self.logger.info(f"缓存已保存到磁盘: {filepath}")
                return True
                
        except Exception as e:
            self.logger.error(f"保存缓存到磁盘失败: {e}")
            return False
    
    def load_from_disk(self, filename: str) -> bool:
        """从磁盘加载缓存"""
        if not self.cache_dir:
            self.logger.warning("未设置缓存目录，无法从磁盘加载")
            return False
        
        try:
            filepath = self.cache_dir / filename
            if not filepath.exists():
                self.logger.error(f"缓存文件不存在: {filepath}")
                return False
            
            with open(filepath, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            with self._lock:
                # 清空当前缓存
                self._cache.clear()
                
                # 加载条目
                for key, entry_data in cache_data.get('entries', {}).items():
                    entry = CacheEntry(
                        key=entry_data['key'],
                        value=entry_data['value'],
                        created_time=entry_data['created_time'],
                        last_access_time=entry_data['last_access_time'],
                        access_count=entry_data['access_count'],
                        ttl=entry_data.get('ttl'),
                        strategy=CacheStrategy(entry_data['strategy']),
                        metadata=entry_data.get('metadata')
                    )
                    
                    # 只加载未过期的条目
                    if not entry.is_expired():
                        self._cache[key] = entry
                
                self._update_stats()
                self.logger.info(f"缓存已从磁盘加载: {filepath}, 条目数: {len(self._cache)}")
                return True
                
        except Exception as e:
            self.logger.error(f"从磁盘加载缓存失败: {e}")
            return False
    
    def atomic_set(self, key: str, value: Any) -> bool:
        """
        原子设置操作（线程安全）
        
        Args:
            key: 缓存键
            value: 要设置的值
            
        Returns:
            是否设置成功
        """
        with self._lock:
            try:
                self.set(key, value)
                return True
            except Exception as e:
                self.logger.error(f"Atomic set failed for key {key}: {e}")
                return False
    
    def atomic_increment(self, key: str, delta: int = 1) -> int:
        """
        原子递增操作（线程安全）
        
        Args:
            key: 缓存键
            delta: 递增量
            
        Returns:
            递增后的新值
        """
        with self._lock:
            current = self.get(key, 0)
            if not isinstance(current, (int, float)):
                current = 0
            new_value = current + delta
            self.set(key, new_value)
            return new_value
    
    def compare_and_swap(self, key: str, expected: Any, new_value: Any) -> bool:
        """
        比较并交换操作（CAS，线程安全）
        
        Args:
            key: 缓存键
            expected: 期望的当前值
            new_value: 新值
            
        Returns:
            是否交换成功
        """
        with self._lock:
            current = self.get(key)
            if current == expected:
                self.set(key, new_value)
                return True
            return False
    
    def atomic_update_dict(self, key: str, updates: Dict[str, Any]) -> bool:
        """
        原子字典更新操作（线程安全）
        
        Args:
            key: 缓存键
            updates: 要更新的字典
            
        Returns:
            是否更新成功
        """
        with self._lock:
            current = self.get(key, {})
            if not isinstance(current, dict):
                self.logger.warning(f"Key {key} is not a dict, cannot update")
                return False
            
            current.update(updates)
            self.set(key, current)
            return True
    
    def atomic_append(self, key: str, value: Any) -> bool:
        """
        原子列表追加操作（线程安全）
        
        Args:
            key: 缓存键
            value: 要追加的值
            
        Returns:
            是否追加成功
        """
        with self._lock:
            current = self.get(key, [])
            if not isinstance(current, list):
                self.logger.warning(f"Key {key} is not a list, cannot append")
                return False
            
            current.append(value)
            self.set(key, current)
            return True
    
    def get_keys_pattern(self, pattern: str) -> List[str]:
        """
        获取匹配模式的键列表（线程安全）
        
        Args:
            pattern: 正则表达式模式
            
        Returns:
            匹配的键列表
        """
        import re
        try:
            regex = re.compile(pattern)
        except re.error as e:
            self.logger.error(f"Invalid regex pattern: {pattern}, error: {e}")
            return []
        
        with self._lock:
            return [key for key in self._cache.keys() if regex.match(key)]
    
    def clear_pattern(self, pattern: str) -> int:
        """
        清除匹配模式的键（线程安全）
        
        Args:
            pattern: 正则表达式模式
            
        Returns:
            清除的条目数
        """
        import re
        try:
            regex = re.compile(pattern)
        except re.error as e:
            self.logger.error(f"Invalid regex pattern: {pattern}, error: {e}")
            return 0
        
        cleared_count = 0
        with self._lock:
            keys_to_remove = [key for key in self._cache.keys() if regex.match(key)]
            for key in keys_to_remove:
                if key in self._cache:
                    del self._cache[key]
                    cleared_count += 1
            
            self._update_stats()
        
        self.logger.info(f"Cleared {cleared_count} entries matching pattern: {pattern}")
        return cleared_count
    
    def shutdown(self):
        """关闭缓存管理器"""
        self._stop_cleanup = True
        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=5)
        
        # 保存缓存到磁盘
        if self.cache_dir:
            self.save_to_disk()
        
        self.logger.info("缓存管理器已关闭")


# 便捷函数
def create_unified_cache_manager(max_size: int = 1000, 
                                default_ttl: Optional[float] = None,
                                strategy: CacheStrategy = CacheStrategy.LRU,
                                cache_dir: Optional[Union[str, Path]] = None) -> UnifiedCacheManager:
    """创建统一缓存管理器的便捷函数"""
    return UnifiedCacheManager(max_size, default_ttl, strategy, cache_dir)


def cache_decorator(ttl: Optional[float] = None, key_prefix: str = ""):
    """缓存装饰器"""
    def decorator(func: Callable):
        def wrapper(*args, **kwargs):
            # 这里需要全局缓存管理器实例
            # 在实际使用中，应该通过依赖注入或其他方式获取
            cache_manager = getattr(func, '_cache_manager', None)
            if cache_manager is None:
                return func(*args, **kwargs)
            
            # 生成缓存键
            cache_key = key_prefix + cache_manager._generate_key(*args, **kwargs)
            
            # 尝试从缓存获取
            cached_result = cache_manager.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # 执行函数并缓存结果
            result = func(*args, **kwargs)
            cache_manager.set(cache_key, result, ttl)
            
            return result
        
        return wrapper
    return decorator 