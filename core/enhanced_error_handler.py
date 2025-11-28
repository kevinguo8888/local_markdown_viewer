#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增强错误处理器 v1.0.0
提供统一的错误处理、分类、恢复和报告机制

作者: LAD Team
创建时间: 2025-08-16
最后更新: 2025-08-16
"""

import sys
import logging
import time
import threading
from collections import deque
import traceback
import json
from pathlib import Path
from typing import Dict, Any, Optional, Union, List, Callable, Type
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import threading
import queue
import os
import builtins


def _safe_open(*args, **kwargs):
    """安全文件打开封装：builtins.open -> io.open -> open。"""
    # 1) builtins.open（标准环境）
    try:
        builtin_open = getattr(builtins, "open", None)
    except Exception:
        builtin_open = None
    if callable(builtin_open):
        return builtin_open(*args, **kwargs)

    # 2) io.open（部分沙箱仍允许）
    try:
        import io as _io_mod
    except Exception:
        _io_mod = None
    io_open = getattr(_io_mod, "open", None) if _io_mod is not None else None
    if callable(io_open):
        return io_open(*args, **kwargs)

    # 3) 回退到普通 open 名称
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


class ErrorSeverity(Enum):
    """错误严重程度枚举"""
    LOW = "low"           # 低严重程度
    MEDIUM = "medium"     # 中等严重程度
    HIGH = "high"         # 高严重程度
    CRITICAL = "critical" # 严重错误


class ErrorCategory(Enum):
    """错误分类枚举"""
    FILE_IO = "file_io"           # 文件I/O错误
    NETWORK = "network"           # 网络错误
    CONFIGURATION = "configuration"  # 配置错误
    RENDERING = "rendering"       # 渲染错误
    CACHE = "cache"              # 缓存错误
    MODULE_IMPORT = "module_import"  # 模块导入错误
    VALIDATION = "validation"    # 验证错误
    SYSTEM = "system"            # 系统错误
    UNKNOWN = "unknown"          # 未知错误


class ErrorRecoveryStrategy(Enum):
    """错误恢复策略枚举"""
    RETRY = "retry"              # 重试
    FALLBACK = "fallback"        # 降级处理
    IGNORE = "ignore"            # 忽略
    ABORT = "abort"              # 中止
    MANUAL = "manual"            # 手动处理


@dataclass
class ErrorContext:
    """错误上下文数据类"""
    timestamp: float
    module: str
    function: str
    line_number: int
    stack_trace: str
    user_context: Optional[Dict[str, Any]] = None
    system_context: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        data = asdict(self)
        data['timestamp_iso'] = datetime.fromtimestamp(self.timestamp).isoformat()
        return data


@dataclass
class ErrorInfo:
    """错误信息数据类"""
    error_id: str
    error_type: str
    error_message: str
    severity: ErrorSeverity
    category: ErrorCategory
    context: ErrorContext
    recovery_strategy: ErrorRecoveryStrategy
    retry_count: int = 0
    max_retries: int = 3
    resolved: bool = False
    resolution_time: Optional[float] = None
    resolution_method: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        data = asdict(self)
        data['severity'] = self.severity.value
        data['category'] = self.category.value
        data['recovery_strategy'] = self.recovery_strategy.value
        data['context'] = self.context.to_dict()
        if self.resolution_time:
            data['resolution_time_iso'] = datetime.fromtimestamp(self.resolution_time).isoformat()
        return data


@dataclass
class ErrorStats:
    """错误统计信息数据类"""
    total_errors: int
    errors_by_severity: Dict[str, int]
    errors_by_category: Dict[str, int]
    errors_by_module: Dict[str, int]
    resolved_errors: int
    unresolved_errors: int
    average_resolution_time: float
    error_rate_per_hour: float
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return asdict(self)


class EnhancedErrorHandler:
    """增强错误处理器"""
    
    def __init__(self, error_log_dir: Optional[Union[str, Path]] = None,
                 max_error_history: int = 1000,
                 config_manager: Optional[Any] = None):
        """
        初始化增强错误处理器
        
        Args:
            error_log_dir: 错误日志目录
            max_error_history: 最大错误历史记录数
            config_manager: 配置管理器实例
        """
        # 初始化基本属性
        self.config_manager = config_manager
        self.error_log_dir = error_log_dir
        self.max_error_history = max_error_history or 1000
        self.error_history = deque(maxlen=self.max_error_history)
        
        # 初始化日志记录器
        self.logger = logging.getLogger(__name__)
        
        # 初始化错误处理策略
        self.error_strategy = "graceful"  # 默认graceful模式
        self.auto_recovery = False  # 默认关闭自动恢复
        self._load_error_strategy()
        
        # 错误处理器映射
        self.error_handlers: Dict[Type[Exception], Callable] = {}
        
        # 恢复策略映射
        self.recovery_strategies: Dict[ErrorCategory, ErrorRecoveryStrategy] = {}
        
        # 错误统计
        self.error_stats = ErrorStats(
            total_errors=0,
            errors_by_severity={},
            errors_by_category={},
            errors_by_module={},
            resolved_errors=0,
            unresolved_errors=0,
            average_resolution_time=0.0,
            error_rate_per_hour=0.0
        )
        
        # 线程安全
        self._lock = threading.RLock()
        
        # 日志
        self.logger = logging.getLogger(__name__)
        
        # 错误队列（用于异步处理）
        self.error_queue = queue.Queue()
        self._processing_thread = None
        self._stop_processing = False
        
        # 初始化
        self._initialize_error_handler()
    
    def _load_error_strategy(self):
        """
        加载错误处理策略配置
        """
        if self.config_manager:
            try:
                # 尝试从配置管理器中获取配置
                if hasattr(self.config_manager, 'get_unified_config'):
                    config = self.config_manager.get_unified_config('error_handling', {})
                else:
                    config = getattr(self.config_manager, '_app_config', {}).get('error_handling', {})
                
                # 设置错误处理策略
                self.error_strategy = config.get('strategy', 'graceful')
                self.auto_recovery = config.get('auto_recovery', False)
                
                self.logger.info(f"加载错误处理策略: {self.error_strategy}, 自动恢复: {self.auto_recovery}")
            except Exception as e:
                self.logger.warning(f"加载错误处理配置失败: {e}, 使用默认值")
                self.error_strategy = "graceful"
                self.auto_recovery = False
        else:
            self.error_strategy = "graceful"
            self.auto_recovery = False
    
    def _initialize_error_handler(self):
        """初始化错误处理器"""
        try:
            # 创建错误日志目录
            if self.error_log_dir:
                self.error_log_dir.mkdir(parents=True, exist_ok=True)
                self.logger.info(f"错误日志目录初始化: {self.error_log_dir}")
            
            # 注册默认错误处理器
            self._register_default_handlers()
            
            # 设置默认恢复策略
            self._setup_default_recovery_strategies()
            
            # 启动异步处理线程
            self._start_processing_thread()
            
            self.logger.info("增强错误处理器初始化完成")
            
        except Exception as e:
            self.logger.error(f"错误处理器初始化失败: {e}")
            raise
    
    def _register_default_handlers(self):
        """注册默认错误处理器"""
        # 文件I/O错误
        self.register_error_handler(FileNotFoundError, self._handle_file_not_found)
        self.register_error_handler(PermissionError, self._handle_permission_error)
        self.register_error_handler(OSError, self._handle_os_error)
        
        # 网络错误
        self.register_error_handler(ConnectionError, self._handle_connection_error)
        self.register_error_handler(TimeoutError, self._handle_timeout_error)
        
        # 配置错误
        self.register_error_handler(KeyError, self._handle_key_error)
        self.register_error_handler(ValueError, self._handle_value_error)
        
        # 导入错误
        self.register_error_handler(ImportError, self._handle_import_error)
        self.register_error_handler(ModuleNotFoundError, self._handle_module_not_found)
        
        # 渲染错误
        self.register_error_handler(SyntaxError, self._handle_syntax_error)
        self.register_error_handler(AttributeError, self._handle_attribute_error)
    
    def _setup_default_recovery_strategies(self):
        """设置默认恢复策略"""
        self.recovery_strategies = {
            ErrorCategory.FILE_IO: ErrorRecoveryStrategy.RETRY,
            ErrorCategory.NETWORK: ErrorRecoveryStrategy.RETRY,
            ErrorCategory.CONFIGURATION: ErrorRecoveryStrategy.FALLBACK,
            ErrorCategory.RENDERING: ErrorRecoveryStrategy.FALLBACK,
            ErrorCategory.CACHE: ErrorRecoveryStrategy.IGNORE,
            ErrorCategory.MODULE_IMPORT: ErrorRecoveryStrategy.FALLBACK,
            ErrorCategory.VALIDATION: ErrorRecoveryStrategy.ABORT,
            ErrorCategory.SYSTEM: ErrorRecoveryStrategy.ABORT,
            ErrorCategory.UNKNOWN: ErrorRecoveryStrategy.MANUAL
        }
    
    def _start_processing_thread(self):
        """启动异步处理线程"""
        try:
            _tm = (os.environ.get('LAD_TEST_MODE') == '1') or ('PYTEST_CURRENT_TEST' in os.environ) or ('PYTEST_PROGRESS_LOG' in os.environ)
        except Exception:
            _tm = False
        if _tm:
            return
        if self._processing_thread is None:
            self._processing_thread = threading.Thread(target=self._process_error_queue, daemon=True)
            self._processing_thread.start()
            self.logger.info("错误异步处理线程已启动")
    
    def _process_error_queue(self):
        """处理错误队列"""
        while not self._stop_processing:
            try:
                # 从队列获取错误信息
                error_info = self.error_queue.get(timeout=1)
                self._process_error_async(error_info)
                self.error_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"处理错误队列异常: {e}")
    
    def _process_error_async(self, error_info: ErrorInfo):
        """异步处理错误"""
        try:
            # 根据恢复策略处理错误
            if error_info.recovery_strategy == ErrorRecoveryStrategy.RETRY:
                self._handle_retry_strategy(error_info)
            elif error_info.recovery_strategy == ErrorRecoveryStrategy.FALLBACK:
                self._handle_fallback_strategy(error_info)
            elif error_info.recovery_strategy == ErrorRecoveryStrategy.IGNORE:
                self._handle_ignore_strategy(error_info)
            elif error_info.recovery_strategy == ErrorRecoveryStrategy.ABORT:
                self._handle_abort_strategy(error_info)
            else:
                self._handle_manual_strategy(error_info)
                
        except Exception as e:
            self.logger.error(f"异步处理错误失败: {e}")
    
    def register_error_handler(self, exception_type: Type[Exception], 
                             handler: Callable[[Exception, ErrorContext], ErrorInfo]):
        """
        注册错误处理器
        
        Args:
            exception_type: 异常类型
            handler: 处理函数
        """
        self.error_handlers[exception_type] = handler
        self.logger.debug(f"注册错误处理器: {exception_type.__name__}")
    
    def handle_error(self, 
                     exception: Exception, 
                     context: Optional[Union[ErrorContext, Dict[str, Any]]] = None,
                     recovery_strategy: Optional[ErrorRecoveryStrategy] = None) -> ErrorInfo:
        """
        处理异常并返回错误信息
        
        Args:
            exception: 要处理的异常
            context: 错误上下文信息，可以是ErrorContext对象或字典
            recovery_strategy: 可选，外部显式指定的恢复策略；如未指定则按分类映射确定
            
        Returns:
            错误信息对象
            
        Raises:
            exception: 在strict模式下会重新抛出异常
        """
        # 处理不同类型的context参数
        if context is None:
            error_context = self._create_error_context()
        elif isinstance(context, dict):
            error_context = self._create_error_context(context)
        elif isinstance(context, ErrorContext):
            error_context = context
        else:
            self.logger.warning(f"不支持的context类型: {type(context).__name__}, 使用默认上下文")
            error_context = self._create_error_context()
            
        # 创建错误信息
        error_info = self._create_default_error_info(exception, error_context)
        
        # 设置恢复策略（外部传入优先，其次按分类映射）
        if recovery_strategy is not None:
            try:
                # 容错：若传入的是字符串，尝试转换
                if isinstance(recovery_strategy, str):
                    recovery_strategy = ErrorRecoveryStrategy(recovery_strategy)
            except Exception:
                recovery_strategy = ErrorRecoveryStrategy.MANUAL
            error_info.recovery_strategy = recovery_strategy
        else:
            error_info.recovery_strategy = self.recovery_strategies.get(
                error_info.category, ErrorRecoveryStrategy.MANUAL
            )
        
        # 记录错误
        with self._lock:
            self._record_error(error_info)
        
        # 记录日志
        self._log_error(error_info)
        
        # 根据策略处理错误
        if self.error_strategy == "strict":
            # 在strict模式下重新抛出异常
            raise exception
            
        # 在graceful模式下尝试自动恢复
        if self.auto_recovery:
            self._try_auto_recovery(error_info)
        
        return error_info
        
    def _create_error_context(self, context: Optional[Dict[str, Any]] = None) -> ErrorContext:
        """
        创建错误上下文
        
        Args:
            context: 可选的用户上下文信息，可以是字典或None
            
        Returns:
            ErrorContext: 错误上下文对象
        """
        # 获取当前调用栈信息
        frame = sys._getframe(2)  # 跳过handle_error和_create_error_context
        
        # 确保user_context是字典类型
        user_context = context if isinstance(context, dict) else {}
        
        return ErrorContext(
            timestamp=time.time(),
            module=frame.f_globals.get('__name__', 'unknown'),
            function=frame.f_code.co_name,
            line_number=frame.f_lineno,
            stack_trace=traceback.format_exc(),
            user_context=user_context if user_context else None,
            system_context=self._get_system_context()
        )
    
    def _get_system_context(self) -> Dict[str, Any]:
        """获取系统上下文"""
        try:
            import psutil
            return {
                'memory_usage': psutil.virtual_memory().percent,
                'cpu_usage': psutil.cpu_percent(),
                'disk_usage': psutil.disk_usage('/').percent,
                'python_version': sys.version,
                'platform': sys.platform
            }
        except Exception:
            return {}
    
    def _find_error_handler(self, exception: Exception) -> Optional[Callable]:
        """查找错误处理器"""
        # 按异常类型层次结构查找
        exception_type = type(exception)
        
        # 直接匹配
        if exception_type in self.error_handlers:
            return self.error_handlers[exception_type]
        
        # 查找父类
        for base_type in exception_type.__mro__[1:]:
            if base_type in self.error_handlers:
                return self.error_handlers[base_type]
        
        return None
    
    def _create_default_error_info(self, exception: Exception, context: ErrorContext) -> ErrorInfo:
        """创建默认错误信息"""
        # 根据异常类型确定分类
        category = self._categorize_exception(exception)
        
        # 根据分类确定严重程度
        severity = self._determine_severity(category, exception)
        
        return ErrorInfo(
            error_id=self._generate_error_id(),
            error_type=type(exception).__name__,
            error_message=str(exception),
            severity=severity,
            category=category,
            context=context,
            recovery_strategy=ErrorRecoveryStrategy.MANUAL
        )
    
    def _categorize_exception(self, exception: Union[Exception, Type[Exception]]) -> ErrorCategory:
        """对异常进行分类
        
        Args:
            exception: 异常实例或异常类型
            
        Returns:
            错误分类
        """
        # 处理异常类型（类）或异常实例
        exception_type = exception if isinstance(exception, type) else type(exception)
        
        # 检查继承关系时，先检查具体的异常类型，再检查基类
        if issubclass(exception_type, ConnectionError):
            return ErrorCategory.NETWORK
        elif issubclass(exception_type, TimeoutError):
            return ErrorCategory.NETWORK
        elif issubclass(exception_type, (FileNotFoundError, PermissionError, OSError)):
            return ErrorCategory.FILE_IO
        elif issubclass(exception_type, (KeyError, ValueError, TypeError)):
            return ErrorCategory.CONFIGURATION
        elif issubclass(exception_type, (ImportError, ModuleNotFoundError)):
            return ErrorCategory.MODULE_IMPORT
        elif issubclass(exception_type, (SyntaxError, AttributeError)):
            return ErrorCategory.RENDERING
        elif issubclass(exception_type, (MemoryError, SystemError)):
            return ErrorCategory.SYSTEM
        else:
            return ErrorCategory.UNKNOWN
    
    def _determine_severity(self, category: ErrorCategory, exception: Exception) -> ErrorSeverity:
        """确定错误严重程度"""
        if category in [ErrorCategory.SYSTEM]:
            return ErrorSeverity.CRITICAL
        elif category in [ErrorCategory.FILE_IO, ErrorCategory.NETWORK]:
            return ErrorSeverity.HIGH
        elif category in [ErrorCategory.CONFIGURATION, ErrorCategory.RENDERING]:
            return ErrorSeverity.MEDIUM
        else:
            return ErrorSeverity.LOW
    
    def _generate_error_id(self) -> str:
        """生成错误ID"""
        return f"ERR_{int(time.time() * 1000)}_{threading.get_ident()}"
    
    def _record_error(self, error_info: ErrorInfo):
        """记录错误"""
        self.error_history.append(error_info)
        self.error_stats.total_errors += 1
        
        # 更新统计信息
        severity_key = error_info.severity.value
        category_key = error_info.category.value
        module_key = error_info.context.module
        
        self.error_stats.errors_by_severity[severity_key] = \
            self.error_stats.errors_by_severity.get(severity_key, 0) + 1
        
        self.error_stats.errors_by_category[category_key] = \
            self.error_stats.errors_by_category.get(category_key, 0) + 1
        
        self.error_stats.errors_by_module[module_key] = \
            self.error_stats.errors_by_module.get(module_key, 0) + 1
        
        # 限制历史记录大小
        if len(self.error_history) > self.max_error_history:
            removed_error = self.error_history.pop(0)
            if removed_error.resolved:
                self.error_stats.resolved_errors -= 1
            else:
                self.error_stats.unresolved_errors -= 1
        
        # 更新未解决错误计数
        if not error_info.resolved:
            self.error_stats.unresolved_errors += 1
    
    def _log_error(self, error_info: ErrorInfo):
        """记录错误日志"""
        log_message = f"错误 {error_info.error_id}: {error_info.error_type} - {error_info.error_message}"
        
        if error_info.severity == ErrorSeverity.CRITICAL:
            self.logger.critical(log_message)
        elif error_info.severity == ErrorSeverity.HIGH:
            self.logger.error(log_message)
        elif error_info.severity == ErrorSeverity.MEDIUM:
            self.logger.warning(log_message)
        else:
            self.logger.info(log_message)
    
    def _handle_retry_strategy(self, error_info: ErrorInfo):
        """处理重试策略"""
        if error_info.retry_count < error_info.max_retries:
            error_info.retry_count += 1
            self.logger.info(f"重试错误 {error_info.error_id} (第{error_info.retry_count}次)")
            # 这里可以实现具体的重试逻辑
        else:
            self.logger.warning(f"错误 {error_info.error_id} 重试次数已达上限")
            self._mark_error_resolved(error_info, "重试失败")
    
    def _handle_fallback_strategy(self, error_info: ErrorInfo):
        """处理降级策略"""
        self.logger.info(f"对错误 {error_info.error_id} 执行降级处理")
        # 这里可以实现具体的降级逻辑
        self._mark_error_resolved(error_info, "降级处理")
    
    def _handle_ignore_strategy(self, error_info: ErrorInfo):
        """处理忽略策略"""
        self.logger.info(f"忽略错误 {error_info.error_id}")
        self._mark_error_resolved(error_info, "忽略处理")
    
    def _handle_abort_strategy(self, error_info: ErrorInfo):
        """处理中止策略"""
        self.logger.error(f"中止处理错误 {error_info.error_id}")
        # 这里可以实现具体的中止逻辑
        self._mark_error_resolved(error_info, "中止处理")
    
    def _handle_manual_strategy(self, error_info: ErrorInfo):
        """处理手动策略"""
        self.logger.warning(f"错误 {error_info.error_id} 需要手动处理")
        # 这里可以发送通知或记录到特殊队列
    
    def _mark_error_resolved(self, error_info: ErrorInfo, resolution_method: str):
        """标记错误为已解决"""
        with self._lock:
            error_info.resolved = True
            error_info.resolution_time = time.time()
            error_info.resolution_method = resolution_method
            
            self.error_stats.resolved_errors += 1
            self.error_stats.unresolved_errors -= 1
            
            # 更新平均解决时间
            if self.error_stats.resolved_errors > 0:
                total_time = sum(
                    (e.resolution_time or 0) - e.context.timestamp
                    for e in self.error_history
                    if e.resolved and e.resolution_time
                )
                self.error_stats.average_resolution_time = total_time / self.error_stats.resolved_errors
    
    def get_error_stats(self) -> ErrorStats:
        """获取错误统计信息"""
        with self._lock:
            # 计算错误率
            if self.error_history:
                first_error_time = self.error_history[0].context.timestamp
                current_time = time.time()
                hours_elapsed = (current_time - first_error_time) / 3600
                if hours_elapsed > 0:
                    self.error_stats.error_rate_per_hour = self.error_stats.total_errors / hours_elapsed
            
            return ErrorStats(
                total_errors=self.error_stats.total_errors,
                errors_by_severity=self.error_stats.errors_by_severity.copy(),
                errors_by_category=self.error_stats.errors_by_category.copy(),
                errors_by_module=self.error_stats.errors_by_module.copy(),
                resolved_errors=self.error_stats.resolved_errors,
                unresolved_errors=self.error_stats.unresolved_errors,
                average_resolution_time=self.error_stats.average_resolution_time,
                error_rate_per_hour=self.error_stats.error_rate_per_hour
            )
    
    def get_error_history(self, limit: int = 100, 
                         severity: Optional[ErrorSeverity] = None,
                         category: Optional[ErrorCategory] = None,
                         resolved: Optional[bool] = None) -> List[Dict[str, Any]]:
        """
        获取错误历史
        
        Args:
            limit: 返回数量限制
            severity: 严重程度过滤
            category: 分类过滤
            resolved: 解决状态过滤
            
        Returns:
            错误历史列表
        """
        with self._lock:
            filtered_errors = list(self.error_history)  # 确保是列表类型
            
            if severity:
                filtered_errors = [e for e in filtered_errors if e.severity == severity]
            
            if category:
                filtered_errors = [e for e in filtered_errors if e.category == category]
            
            if resolved is not None:
                filtered_errors = [e for e in filtered_errors if e.resolved == resolved]
            
            return [error.to_dict() for error in filtered_errors[-limit:]]
    
    def clear_error_history(self):
        """清空错误历史"""
        with self._lock:
            self.error_history.clear()
            self.error_stats = ErrorStats(
                total_errors=0,
                errors_by_severity={},
                errors_by_category={},
                errors_by_module={},
                resolved_errors=0,
                unresolved_errors=0,
                average_resolution_time=0.0,
                error_rate_per_hour=0.0
            )
        self.logger.info("错误历史已清空")
    
    def save_error_report(self, filename: Optional[str] = None) -> bool:
        """保存错误报告"""
        if not self.error_log_dir:
            return False
        
        try:
            filename = filename or f"error_report_{int(time.time())}.json"
            filepath = self.error_log_dir / filename
            
            report_data = {
                'metadata': {
                    'version': '1.0.0',
                    'created_time': datetime.now().isoformat(),
                    'total_errors': self.error_stats.total_errors
                },
                'stats': self.get_error_stats().to_dict(),
                'recent_errors': self.get_error_history(50)
            }
            
            with _safe_open(filepath, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"错误报告已保存: {filepath}")
            return True
            
        except Exception as e:
            self.logger.error(f"保存错误报告失败: {e}")
            return False
    
    def shutdown(self):
        """关闭错误处理器"""
        self._stop_processing = True
        if self._processing_thread:
            self._processing_thread.join(timeout=5)
        
        # 保存错误报告
        self.save_error_report()
        
        self.logger.info("增强错误处理器已关闭")
    
    # 默认错误处理器方法
    def _handle_file_not_found(self, exception: Exception, context: ErrorContext) -> ErrorInfo:
        return ErrorInfo(
            error_id=self._generate_error_id(),
            error_type="FileNotFoundError",
            error_message=str(exception),
            severity=ErrorSeverity.HIGH,
            category=ErrorCategory.FILE_IO,
            context=context,
            recovery_strategy=ErrorRecoveryStrategy.RETRY
        )
    
    def _handle_permission_error(self, exception: Exception, context: ErrorContext) -> ErrorInfo:
        return ErrorInfo(
            error_id=self._generate_error_id(),
            error_type="PermissionError",
            error_message=str(exception),
            severity=ErrorSeverity.HIGH,
            category=ErrorCategory.FILE_IO,
            context=context,
            recovery_strategy=ErrorRecoveryStrategy.ABORT
        )
    
    def _handle_os_error(self, exception: Exception, context: ErrorContext) -> ErrorInfo:
        return ErrorInfo(
            error_id=self._generate_error_id(),
            error_type="OSError",
            error_message=str(exception),
            severity=ErrorSeverity.MEDIUM,
            category=ErrorCategory.FILE_IO,
            context=context,
            recovery_strategy=ErrorRecoveryStrategy.RETRY
        )
    
    def _handle_connection_error(self, exception: Exception, context: ErrorContext) -> ErrorInfo:
        return ErrorInfo(
            error_id=self._generate_error_id(),
            error_type="ConnectionError",
            error_message=str(exception),
            severity=ErrorSeverity.HIGH,
            category=ErrorCategory.NETWORK,
            context=context,
            recovery_strategy=ErrorRecoveryStrategy.RETRY
        )
    
    def _handle_timeout_error(self, exception: Exception, context: ErrorContext) -> ErrorInfo:
        return ErrorInfo(
            error_id=self._generate_error_id(),
            error_type="TimeoutError",
            error_message=str(exception),
            severity=ErrorSeverity.MEDIUM,
            category=ErrorCategory.NETWORK,
            context=context,
            recovery_strategy=ErrorRecoveryStrategy.RETRY
        )
    
    def _handle_key_error(self, exception: Exception, context: ErrorContext) -> ErrorInfo:
        return ErrorInfo(
            error_id=self._generate_error_id(),
            error_type="KeyError",
            error_message=str(exception),
            severity=ErrorSeverity.MEDIUM,
            category=ErrorCategory.CONFIGURATION,
            context=context,
            recovery_strategy=ErrorRecoveryStrategy.FALLBACK
        )
    
    def _handle_value_error(self, exception: Exception, context: ErrorContext) -> ErrorInfo:
        return ErrorInfo(
            error_id=self._generate_error_id(),
            error_type="ValueError",
            error_message=str(exception),
            severity=ErrorSeverity.MEDIUM,
            category=ErrorCategory.CONFIGURATION,
            context=context,
            recovery_strategy=ErrorRecoveryStrategy.FALLBACK
        )
    
    def _handle_import_error(self, exception: Exception, context: ErrorContext) -> ErrorInfo:
        return ErrorInfo(
            error_id=self._generate_error_id(),
            error_type="ImportError",
            error_message=str(exception),
            severity=ErrorSeverity.MEDIUM,
            category=ErrorCategory.MODULE_IMPORT,
            context=context,
            recovery_strategy=ErrorRecoveryStrategy.FALLBACK
        )
    
    def _handle_module_not_found(self, exception: Exception, context: ErrorContext) -> ErrorInfo:
        return ErrorInfo(
            error_id=self._generate_error_id(),
            error_type="ModuleNotFoundError",
            error_message=str(exception),
            severity=ErrorSeverity.MEDIUM,
            category=ErrorCategory.MODULE_IMPORT,
            context=context,
            recovery_strategy=ErrorRecoveryStrategy.FALLBACK
        )
    
    def _handle_syntax_error(self, exception: Exception, context: ErrorContext) -> ErrorInfo:
        return ErrorInfo(
            error_id=self._generate_error_id(),
            error_type="SyntaxError",
            error_message=str(exception),
            severity=ErrorSeverity.HIGH,
            category=ErrorCategory.RENDERING,
            context=context,
            recovery_strategy=ErrorRecoveryStrategy.FALLBACK
        )
    
    def _handle_attribute_error(self, exception: Exception, context: ErrorContext) -> ErrorInfo:
        return ErrorInfo(
            error_id=self._generate_error_id(),
            error_type="AttributeError",
            error_message=str(exception),
            severity=ErrorSeverity.MEDIUM,
            category=ErrorCategory.RENDERING,
            context=context,
            recovery_strategy=ErrorRecoveryStrategy.FALLBACK
        )
    
    def _create_basic_error_info(self, exception: Exception, message: str) -> ErrorInfo:
        """创建基本错误信息"""
        return ErrorInfo(
            error_id=self._generate_error_id(),
            error_type=type(exception).__name__,
            error_message=message,
            severity=ErrorSeverity.LOW,
            category=ErrorCategory.UNKNOWN,
            context=ErrorContext(
                timestamp=time.time(),
                module="unknown",
                function="unknown",
                line_number=0,
                stack_trace=""
            ),
            recovery_strategy=ErrorRecoveryStrategy.MANUAL
        )


# 便捷函数
def create_enhanced_error_handler(error_log_dir: Optional[Union[str, Path]] = None,
                                max_error_history: int = 1000,
                                config_manager: Optional[Any] = None) -> EnhancedErrorHandler:
    """创建增强错误处理器的便捷函数"""
    return EnhancedErrorHandler(error_log_dir, max_error_history, config_manager)


# 错误处理装饰器
def handle_errors(recovery_strategy: Optional[ErrorRecoveryStrategy] = None,
                 context: Optional[Dict[str, Any]] = None):
    """错误处理装饰器"""
    def decorator(func: Callable):
        def wrapper(*args, **kwargs):
            # 获取错误处理器实例
            error_handler = getattr(func, '_error_handler', None)
            if error_handler is None:
                return func(*args, **kwargs)
            
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # 处理错误
                error_info = error_handler.handle_error(e, context, recovery_strategy)
                
                # 根据恢复策略决定是否重新抛出异常
                if error_info.recovery_strategy == ErrorRecoveryStrategy.ABORT:
                    raise
                elif error_info.recovery_strategy == ErrorRecoveryStrategy.IGNORE:
                    return None
                else:
                    # 其他策略可以返回默认值或重新抛出
                    raise
        
        return wrapper
    return decorator 