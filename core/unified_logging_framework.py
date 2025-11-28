#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一日志框架 v1.0.0
提供统一的日志记录、格式化、输出管理和监控功能

作者: LAD Team
创建时间: 2025-08-17
最后更新: 2025-08-17
"""

import os
import sys
import time
import json
import logging
import logging.handlers
import builtins
from pathlib import Path
from typing import Dict, Any, Optional, Union, List, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import threading
import queue
import traceback

# 导入现有组件
from .enhanced_error_handler import EnhancedErrorHandler, ErrorCategory, ErrorSeverity
from .unified_cache_manager import UnifiedCacheManager, CacheStrategy


def _safe_open(*args, **kwargs):
    """统一日志框架使用的安全 open 封装。"""
    # 1) 优先 builtins.open
    try:
        builtin_open = getattr(builtins, "open", None)
    except Exception:
        builtin_open = None
    if callable(builtin_open):
        return builtin_open(*args, **kwargs)

    # 2) 其次 io.open
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


class LogLevel(Enum):
    """日志级别枚举"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogOutput(Enum):
    """日志输出方式枚举"""
    CONSOLE = "console"
    FILE = "file"
    SYSLOG = "syslog"
    NETWORK = "network"
    DATABASE = "database"


class LogFormat(Enum):
    """日志格式枚举"""
    SIMPLE = "simple"
    DETAILED = "detailed"
    JSON = "json"
    STRUCTURED = "structured"


@dataclass
class LogContext:
    """日志上下文数据类"""
    timestamp: float
    level: LogLevel
    module: str
    function: str
    line_number: int
    thread_id: int
    process_id: int
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    extra_data: Optional[Dict[str, Any]] = None


@dataclass
class LogMetrics:
    """日志指标数据类"""
    total_logs: int
    logs_by_level: Dict[str, int]
    logs_by_module: Dict[str, int]
    average_log_size: float
    error_rate: float
    performance_impact: float


class StructuredFormatter(logging.Formatter):
    """结构化日志格式化器"""
    
    def __init__(self, format_type: LogFormat = LogFormat.STRUCTURED):
        super().__init__()
        self.format_type = format_type
    
    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录"""
        if self.format_type == LogFormat.JSON:
            return self._format_json(record)
        elif self.format_type == LogFormat.STRUCTURED:
            return self._format_structured(record)
        elif self.format_type == LogFormat.DETAILED:
            return self._format_detailed(record)
        else:
            return self._format_simple(record)
    
    def _format_json(self, record: logging.LogRecord) -> str:
        """JSON格式"""
        log_data = {
            'timestamp': time.time(),
            'level': record.levelname,
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
            'message': record.getMessage(),
            'thread': record.thread,
            'process': record.process
        }
        
        if hasattr(record, 'extra_data'):
            log_data['extra'] = record.extra_data
        
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, ensure_ascii=False)
    
    def _format_structured(self, record: logging.LogRecord) -> str:
        """结构化格式"""
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(record.created))
        level = f"[{record.levelname:8}]"
        module = f"[{record.module:15}]"
        function = f"[{record.funcName:20}]"
        line = f"[{record.lineno:4}]"
        message = record.getMessage()
        
        structured = f"{timestamp} {level} {module} {function} {line} {message}"
        
        if hasattr(record, 'extra_data'):
            structured += f" | {json.dumps(record.extra_data, ensure_ascii=False)}"
        
        if record.exc_info:
            structured += f"\n{self.formatException(record.exc_info)}"
        
        return structured
    
    def _format_detailed(self, record: logging.LogRecord) -> str:
        """详细格式"""
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S.%f', time.localtime(record.created))
        level = record.levelname
        module = record.module
        function = record.funcName
        line = record.lineno
        thread = record.thread
        process = record.process
        message = record.getMessage()
        
        detailed = f"[{timestamp}] [{level}] [{module}.{function}:{line}] [T:{thread}] [P:{process}] {message}"
        
        if hasattr(record, 'extra_data'):
            detailed += f"\nExtra Data: {json.dumps(record.extra_data, indent=2, ensure_ascii=False)}"
        
        if record.exc_info:
            detailed += f"\nException:\n{self.formatException(record.exc_info)}"
        
        return detailed
    
    def _format_simple(self, record: logging.LogRecord) -> str:
        """简单格式"""
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(record.created))
        level = record.levelname
        message = record.getMessage()
        
        return f"[{timestamp}] [{level}] {message}"


class UnifiedLoggingFramework:
    """统一日志框架管理器"""
    
    def __init__(self, 
                 log_dir: Optional[Path] = None,
                 log_level: LogLevel = LogLevel.INFO,
                 output_formats: List[LogOutput] = None,
                 log_format: LogFormat = LogFormat.STRUCTURED,
                 max_file_size: int = 10 * 1024 * 1024,  # 10MB
                 backup_count: int = 5,
                 enable_performance_monitoring: bool = True):
        """
        初始化统一日志框架
        
        Args:
            log_dir: 日志目录
            log_level: 日志级别
            output_formats: 输出格式列表
            log_format: 日志格式
            max_file_size: 最大文件大小
            backup_count: 备份文件数量
            enable_performance_monitoring: 是否启用性能监控
        """
        self.logger = logging.getLogger(__name__)
        
        # 配置参数
        self.log_level = log_level
        self.output_formats = output_formats or [LogOutput.CONSOLE, LogOutput.FILE]
        self.log_format = log_format
        self.max_file_size = max_file_size
        self.backup_count = backup_count
        self.enable_performance_monitoring = enable_performance_monitoring
        self._fast_mode = (os.environ.get("LAD_TEST_MODE") == "1" or os.environ.get("LAD_QA_FAST") == "1")
        
        # 日志目录
        if log_dir is None:
            log_dir = Path(__file__).parent.parent / "logs"
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 组件集成
        self.error_handler = EnhancedErrorHandler(
            error_log_dir=self.log_dir / "errors",
            max_error_history=100
        )
        
        self.cache_manager = UnifiedCacheManager(
            max_size=1000,
            strategy=CacheStrategy.LRU
        )
        
        # 日志记录器
        self.loggers: Dict[str, logging.Logger] = {}
        
        # 性能监控
        self.log_metrics = LogMetrics(
            total_logs=0,
            logs_by_level={level.value: 0 for level in LogLevel},
            logs_by_module={},
            average_log_size=0.0,
            error_rate=0.0,
            performance_impact=0.0
        )
        
        # 线程安全
        self._lock = threading.Lock()
        self._metrics_lock = threading.Lock()
        
        # 初始化日志系统
        self._setup_logging_system()
        
        # 启动性能监控线程
        if self.enable_performance_monitoring and not self._fast_mode:
            self._start_performance_monitoring()
        
        self.logger.info("统一日志框架初始化完成")
    
    def _setup_logging_system(self):
        """设置日志系统"""
        try:
            # 创建根日志记录器
            root_logger = logging.getLogger()
            root_logger.setLevel(getattr(logging, self.log_level.value))
            
            # 清除现有处理器
            for handler in root_logger.handlers[:]:
                root_logger.removeHandler(handler)
            
            # 添加处理器
            for output_format in self.output_formats:
                handler = self._create_handler(output_format)
                if handler:
                    root_logger.addHandler(handler)
            
            # 设置异常处理器
            sys.excepthook = self._handle_uncaught_exception
            
        except Exception as e:
            print(f"设置日志系统失败: {e}")
    
    def _create_handler(self, output_format: LogOutput) -> Optional[logging.Handler]:
        """创建日志处理器"""
        try:
            if output_format == LogOutput.CONSOLE:
                return self._create_console_handler()
            elif output_format == LogOutput.FILE:
                return self._create_file_handler()
            elif output_format == LogOutput.SYSLOG:
                return self._create_syslog_handler()
            elif output_format == LogOutput.NETWORK:
                return self._create_network_handler()
            elif output_format == LogOutput.DATABASE:
                return self._create_database_handler()
            else:
                return None
        except Exception as e:
            self.logger.error(f"创建{output_format.value}处理器失败: {e}")
            return None
    
    def _create_console_handler(self) -> logging.StreamHandler:
        """创建控制台处理器"""
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredFormatter(self.log_format))
        return handler
    
    def _create_file_handler(self) -> logging.handlers.RotatingFileHandler:
        """创建文件处理器"""
        log_file = self.log_dir / "application.log"
        handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=self.max_file_size,
            backupCount=self.backup_count,
            encoding='utf-8'
        )
        handler.setFormatter(StructuredFormatter(self.log_format))
        return handler
    
    def _create_syslog_handler(self) -> logging.handlers.SysLogHandler:
        """创建系统日志处理器"""
        try:
            handler = logging.handlers.SysLogHandler()
            handler.setFormatter(StructuredFormatter(self.log_format))
            return handler
        except Exception:
            # 如果系统日志不可用，返回None
            return None
    
    def _create_network_handler(self) -> logging.handlers.SocketHandler:
        """创建网络处理器"""
        try:
            handler = logging.handlers.SocketHandler('localhost', 19996)
            handler.setFormatter(StructuredFormatter(self.log_format))
            return handler
        except Exception:
            # 如果网络不可用，返回None
            return None
    
    def _create_database_handler(self) -> logging.Handler:
        """创建数据库处理器"""
        # 这里可以实现数据库日志处理器
        # 暂时返回None
        return None
    
    def _handle_uncaught_exception(self, exc_type, exc_value, exc_traceback):
        """处理未捕获的异常"""
        if issubclass(exc_type, KeyboardInterrupt):
            # 忽略键盘中断
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        
        # 记录未捕获的异常
        self.logger.critical(
            "未捕获的异常",
            exc_info=(exc_type, exc_value, exc_traceback)
        )
    
    def get_logger(self, name: str, level: Optional[LogLevel] = None) -> logging.Logger:
        """获取日志记录器"""
        with self._lock:
            if name not in self.loggers:
                logger = logging.getLogger(name)
                if level:
                    logger.setLevel(getattr(logging, level.value))
                self.loggers[name] = logger
            
            return self.loggers[name]
    
    def log_with_context(self, 
                        level: LogLevel,
                        message: str,
                        module: str,
                        function: str,
                        line_number: int,
                        extra_data: Optional[Dict[str, Any]] = None,
                        exception: Optional[Exception] = None):
        """带上下文的日志记录"""
        try:
            # 创建日志上下文
            context = LogContext(
                timestamp=time.time(),
                level=level,
                module=module,
                function=function,
                line_number=line_number,
                thread_id=threading.get_ident(),
                process_id=os.getpid(),
                extra_data=extra_data
            )
            
            # 获取日志记录器
            logger = self.get_logger(module)
            
            # 记录日志
            log_method = getattr(logger, level.value.lower())
            
            if exception:
                log_method(message, exc_info=True, extra={'context': context})
            else:
                log_method(message, extra={'context': context})
            
            # 更新指标
            self._update_metrics(context, len(message))
            
            # 缓存日志上下文
            self.cache_manager.set(f"log_context_{context.timestamp}", context, ttl=3600)
            
        except Exception as e:
            # 如果日志记录失败，使用print作为后备
            print(f"日志记录失败: {e}")
            print(f"原始消息: [{level.value}] {module}.{function}:{line_number} - {message}")
    
    def _update_metrics(self, context: LogContext, message_size: int):
        """更新日志指标"""
        with self._metrics_lock:
            self.log_metrics.total_logs += 1
            
            # 按级别统计
            level_key = context.level.value
            self.log_metrics.logs_by_level[level_key] += 1
            
            # 按模块统计
            module_key = context.module
            if module_key not in self.log_metrics.logs_by_module:
                self.log_metrics.logs_by_module[module_key] = 0
            self.log_metrics.logs_by_module[module_key] += 1
            
            # 计算平均日志大小
            total_size = self.log_metrics.average_log_size * (self.log_metrics.total_logs - 1) + message_size
            self.log_metrics.average_log_size = total_size / self.log_metrics.total_logs
            
            # 计算错误率
            error_count = (self.log_metrics.logs_by_level.get(LogLevel.ERROR.value, 0) + 
                          self.log_metrics.logs_by_level.get(LogLevel.CRITICAL.value, 0))
            self.log_metrics.error_rate = error_count / self.log_metrics.total_logs if self.log_metrics.total_logs > 0 else 0.0
    
    def _start_performance_monitoring(self):
        """启动性能监控线程"""
        def monitor_performance():
            while True:
                try:
                    time.sleep(60)  # 每分钟检查一次
                    self._check_performance_impact()
                except Exception as e:
                    print(f"性能监控失败: {e}")
        
        monitor_thread = threading.Thread(target=monitor_performance, daemon=True)
        monitor_thread.start()
    
    def _check_performance_impact(self):
        """检查性能影响"""
        try:
            # 计算日志记录对性能的影响
            # 这里可以实现更复杂的性能分析逻辑
            current_time = time.time()
            
            # 简单的性能影响计算（示例）
            if self.log_metrics.total_logs > 1000:
                self.log_metrics.performance_impact = 0.1  # 10%的性能影响
            elif self.log_metrics.total_logs > 100:
                self.log_metrics.performance_impact = 0.05  # 5%的性能影响
            else:
                self.log_metrics.performance_impact = 0.01  # 1%的性能影响
            
        except Exception as e:
            self.logger.error(f"检查性能影响失败: {e}")
    
    def get_log_metrics(self) -> LogMetrics:
        """获取日志指标"""
        with self._metrics_lock:
            return LogMetrics(
                total_logs=self.log_metrics.total_logs,
                logs_by_level=self.log_metrics.logs_by_level.copy(),
                logs_by_module=self.log_metrics.logs_by_module.copy(),
                average_log_size=self.log_metrics.average_log_size,
                error_rate=self.log_metrics.error_rate,
                performance_impact=self.log_metrics.performance_impact
            )
    
    def export_logs(self, 
                    start_time: Optional[float] = None,
                    end_time: Optional[float] = None,
                    level: Optional[LogLevel] = None,
                    module: Optional[str] = None,
                    output_file: Optional[Path] = None) -> str:
        """导出日志"""
        try:
            # 读取日志文件
            log_file = self.log_dir / "application.log"
            if not log_file.exists():
                return "日志文件不存在"
            
            exported_logs = []
            with _safe_open(log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if self._should_export_line(line, start_time, end_time, level, module):
                        exported_logs.append(line)
            
            # 写入输出文件
            if output_file is None:
                output_file = self.log_dir / f"exported_logs_{int(time.time())}.log"
            
            with _safe_open(output_file, 'w', encoding='utf-8') as f:
                f.writelines(exported_logs)
            
            return f"日志导出完成，共{len(exported_logs)}行，保存到: {output_file}"
            
        except Exception as e:
            return f"日志导出失败: {e}"
    
    def _should_export_line(self, 
                           line: str,
                           start_time: Optional[float],
                           end_time: Optional[float],
                           level: Optional[LogLevel],
                           module: Optional[str]) -> bool:
        """判断是否应该导出该行日志"""
        try:
            # 解析日志行（这里需要根据实际日志格式调整）
            if start_time or end_time or level or module:
                # 简单的解析逻辑，实际使用时需要更复杂的解析
                return True
            return True
        except Exception:
            return True
    
    def clear_logs(self, days: int = 30) -> str:
        """清理旧日志"""
        try:
            current_time = time.time()
            cutoff_time = current_time - (days * 24 * 3600)
            
            cleared_count = 0
            for log_file in self.log_dir.glob("*.log*"):
                if log_file.stat().st_mtime < cutoff_time:
                    log_file.unlink()
                    cleared_count += 1
            
            return f"清理完成，删除了{cleared_count}个旧日志文件"
            
        except Exception as e:
            return f"清理日志失败: {e}"
    
    def shutdown(self):
        """关闭日志框架"""
        try:
            # 关闭所有处理器
            root_logger = logging.getLogger()
            for handler in root_logger.handlers[:]:
                handler.close()
                root_logger.removeHandler(handler)
            
            # 关闭组件
            if hasattr(self, 'error_handler'):
                self.error_handler.shutdown()
            
            if hasattr(self, 'cache_manager'):
                self.cache_manager.shutdown()
            
            self.logger.info("统一日志框架已关闭")
            
        except Exception as e:
            print(f"关闭日志框架时出现错误: {e}")
    
    def __del__(self):
        """析构函数"""
        try:
            self.shutdown()
        except:
            pass


# 便捷的日志记录函数
def log_debug(message: str, module: str, function: str, line_number: int, **kwargs):
    """记录调试日志"""
    if hasattr(log_debug, '_framework'):
        log_debug._framework.log_with_context(
            LogLevel.DEBUG, message, module, function, line_number, kwargs
        )

def log_info(message: str, module: str, function: str, line_number: int, **kwargs):
    """记录信息日志"""
    if hasattr(log_info, '_framework'):
        log_info._framework.log_with_context(
            LogLevel.INFO, message, module, function, line_number, kwargs
        )

def log_warning(message: str, module: str, function: str, line_number: int, **kwargs):
    """记录警告日志"""
    if hasattr(log_warning, '_framework'):
        log_warning._framework.log_with_context(
            LogLevel.WARNING, message, module, function, line_number, kwargs
        )

def log_error(message: str, module: str, function: str, line_number: int, **kwargs):
    """记录错误日志"""
    if hasattr(log_error, '_framework'):
        log_error._framework.log_with_context(
            LogLevel.ERROR, message, module, function, line_number, kwargs
        )

def log_critical(message: str, module: str, function: str, line_number: int, **kwargs):
    """记录严重错误日志"""
    if hasattr(log_critical, '_framework'):
        log_critical._framework.log_with_context(
            LogLevel.CRITICAL, message, module, function, line_number, kwargs
        )


def setup_logging_framework(framework: UnifiedLoggingFramework):
    """设置日志框架到便捷函数"""
    log_debug._framework = framework
    log_info._framework = framework
    log_warning._framework = framework
    log_error._framework = framework
    log_critical._framework = framework 