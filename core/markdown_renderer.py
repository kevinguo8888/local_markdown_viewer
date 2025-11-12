#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
混合架构Markdown渲染器模块 v2.1.0
负责将Markdown内容渲染为HTML，支持动态模块导入和混合架构
支持文件渲染、内容渲染、自定义选项等功能
重构：集成DynamicModuleImporter，实现动态导入+统一路径解析的混合方案
优化版本：根据used_fallback状态选择渲染策略，增强日志记录和错误处理

作者: LAD Team
创建时间: 2025-08-02
最后更新: 2025-09-01
"""

import os
import sys
import logging
import hashlib
import time
from pathlib import Path
from typing import Dict, Any, Optional, Union, Tuple, List
from functools import lru_cache
from datetime import datetime
import builtins

# 导入统一缓存管理器
from .unified_cache_manager import UnifiedCacheManager, CacheStrategy
from .cache_invalidation_manager import CacheInvalidationManager, InvalidationTrigger
from .enhanced_error_handler import EnhancedErrorHandler, ErrorRecoveryStrategy



# 备用markdown库
try:
    import markdown
    MARKDOWN_AVAILABLE = True
except ImportError:
    MARKDOWN_AVAILABLE = False
    logging.warning("无法导入markdown库，将使用基本文本渲染")

try:
    from utils.config_manager import ConfigManager
    from core.file_resolver import FileResolver
    from core.dynamic_module_importer import DynamicModuleImporter
except ImportError:
    # 如果导入失败，尝试相对导入
    try:
        from ..utils.config_manager import ConfigManager
        from ..core.file_resolver import FileResolver
        from ..core.dynamic_module_importer import DynamicModuleImporter
    except ImportError:
        # 最后尝试绝对路径导入
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from utils.config_manager import ConfigManager
        from core.file_resolver import FileResolver
        from core.dynamic_module_importer import DynamicModuleImporter


class HybridMarkdownRenderer:
    """
    混合架构Markdown渲染器类
    提供Markdown内容渲染功能，支持动态模块导入和多种渲染模式
    重构：集成DynamicModuleImporter，实现动态导入+统一路径解析的混合方案
    优化版本：根据used_fallback状态选择渲染策略，增强日志记录和错误处理
    """
    
    def __init__(self, config_manager: Optional[ConfigManager] = None):
        """
        初始化混合架构Markdown渲染器
        
        Args:
            config_manager: 配置管理器实例
        """
        self.config_manager = config_manager or ConfigManager()
        self.logger = logging.getLogger(__name__)
        
        # 初始化文件解析器
        self.file_resolver = FileResolver(config_manager)
        
        self.snapshot_manager = None
        self.performance_metrics = None
        
        # 初始化动态模块导入器
        self.module_importer = DynamicModuleImporter(config_manager)
        
        # 统一缓存管理器
        self.cache_manager = UnifiedCacheManager(
            max_size=500,  # 增加缓存大小
            default_ttl=3600,  # 默认1小时过期
            strategy=CacheStrategy.LRU,
            cache_dir=Path(__file__).parent.parent / "cache" / "renderer"
        )
        
        # 缓存失效管理器
        self.invalidation_manager = CacheInvalidationManager(
            self.cache_manager,
            invalidation_dir=Path(__file__).parent.parent / "cache" / "invalidation"
        )
        
        # 增强错误处理器
        self.error_handler = EnhancedErrorHandler(
            error_log_dir=Path(__file__).parent.parent / "logs" / "errors",
            max_error_history=500
        )
        
        # 兼容性：保留旧缓存接口
        self._render_cache = {}
        self._cache_max_size = 100
        
        # 渲染选项
        self.default_options = {
            'enable_zoom': True,
            'enable_syntax_highlight': True,
            'theme': 'default',
            'max_content_length': 5 * 1024 * 1024,  # 5MB
            'cache_enabled': True,
            'fallback_to_text': True,
            'use_dynamic_import': True  # 新增：控制是否使用动态导入
        }
        
        # 根据配置更新选项
        self._update_options_from_config()
        
        # 检查可用性
        self._check_availability()
    
    def set_snapshot_manager(self, snapshot_manager: Any) -> None:
        self.snapshot_manager = snapshot_manager
        self.module_importer.set_snapshot_manager(snapshot_manager)

    def set_performance_metrics(self, metrics: Any) -> None:
        self.performance_metrics = metrics
        self.module_importer.set_performance_metrics(metrics)
        
    def _update_options_from_config(self):
        """根据配置更新渲染选项"""
        markdown_config = self.config_manager.get_markdown_config()
        
        # 更新动态导入设置
        if 'use_dynamic_import' in markdown_config:
            self.default_options['use_dynamic_import'] = markdown_config['use_dynamic_import']
        
        # 更新缓存设置
        if 'cache_enabled' in markdown_config:
            self.default_options['cache_enabled'] = markdown_config['cache_enabled']
        
        # 更新降级设置
        if 'fallback_enabled' in markdown_config:
            self.default_options['fallback_to_text'] = markdown_config['fallback_enabled']
        
        # 更新其他设置
        for key in ['enable_zoom', 'enable_syntax_highlight', 'theme', 'max_content_length']:
            if key in markdown_config:
                self.default_options[key] = markdown_config[key]
    
    def _check_availability(self):
        """检查渲染组件的可用性 - 优化版本：处理Importer标准化结果格式"""
        # 检查动态导入的模块
        if self.default_options.get('use_dynamic_import', True):
            markdown_processor_result = self.module_importer.import_module('markdown_processor', ['markdown'])
            
            # 优化1: 处理Importer返回的标准化结果格式
            self.markdown_processor_available = markdown_processor_result.get('success', False)
            self._markdown_processor_functions = markdown_processor_result.get('functions', {})
            self._import_result_details = markdown_processor_result  # 保存完整结果供后续使用
            
            # 优化2: 根据used_fallback状态记录详细信息
            if markdown_processor_result.get('used_fallback', False):
                self.logger.info(f"Fallback命中: 使用{markdown_processor_result.get('module', 'unknown')}模块")
                self.logger.info(f"  - Fallback原因: {markdown_processor_result.get('fallback_reason', '未知')}")
                self.logger.info(f"  - 模块路径: {markdown_processor_result.get('path', 'unknown')}")
            elif self.markdown_processor_available:
                self.logger.info("动态导入markdown_processor成功")
                self.logger.info(f"  - 模块路径: {markdown_processor_result.get('path', 'unknown')}")
                self.logger.info(f"  - 可用函数: {list(self._markdown_processor_functions.keys())}")
                self.logger.info(f"  - 验证状态: {markdown_processor_result.get('validation_details', '未知')}")
            else:
                self.logger.warning(f"动态导入markdown_processor失败")
                self.logger.warning(f"  - 错误码: {markdown_processor_result.get('error_code', '未知')}")
                self.logger.warning(f"  - 错误消息: {markdown_processor_result.get('message', '未知')}")
                if markdown_processor_result.get('missing_functions'):
                    self.logger.warning(f"  - 缺失函数: {markdown_processor_result['missing_functions']}")
                if markdown_processor_result.get('non_callable_functions'):
                    self.logger.warning(f"  - 不可调用函数: {markdown_processor_result['non_callable_functions']}")
                self._markdown_processor_functions = {}
        
        # 检查备用模块
        self.markdown_available = MARKDOWN_AVAILABLE
        
        # 优化3: 增强状态记录，包含更多上下文信息
        self.logger.info(f"Markdown处理器可用: {getattr(self, 'markdown_processor_available', False)}")
        self.logger.info(f"备用Markdown库可用: {self.markdown_available}")
        
        if not self.markdown_processor_available and not self.markdown_available:
            self.logger.warning("所有Markdown渲染组件都不可用，将使用纯文本渲染")
    
    def render(self, markdown_content: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        渲染Markdown内容为HTML
        
        Args:
            markdown_content: Markdown内容字符串
            options: 渲染选项
            
        Returns:
            渲染结果字典
        """
        start_time = time.time()
        
        try:
            # 检查输入内容
            if markdown_content is None:
                return self._render_error_result("内容为空", "输入内容不能为None")
            
            # 合并选项
            render_options = {**self.default_options, **(options or {})}
            
            # 检查内容长度
            if len(markdown_content) > render_options['max_content_length']:
                return self._render_error_result(
                    "内容过长",
                    f"内容长度({len(markdown_content)})超过限制({render_options['max_content_length']})"
                )
            
            # 检查缓存
            if render_options['cache_enabled']:
                cache_key = self._generate_cache_key(markdown_content, render_options)
                
                # 使用统一缓存管理器
                cached_result = self.cache_manager.get(cache_key)
                if cached_result is not None:
                    cached_result = cached_result.copy()
                    cached_result['cached'] = True
                    cached_result['render_time'] = time.time() - start_time
                    cached_result['cache_hit'] = True
                    return cached_result
                
                # 兼容性：检查旧缓存
                if cache_key in self._render_cache:
                    cached_result = self._render_cache[cache_key].copy()
                    cached_result['cached'] = True
                    cached_result['render_time'] = time.time() - start_time
                    return cached_result
            
            # 执行渲染
            result = self._render_content(markdown_content, render_options)
            result['render_time'] = time.time() - start_time
            
            # 缓存结果
            if render_options['cache_enabled']:
                # 使用统一缓存管理器
                self.cache_manager.set(cache_key, result, ttl=3600)  # 1小时过期
                
                # 兼容性：同时更新旧缓存
                self._cache_result(cache_key, result)
            
            return result
            
        except Exception as e:
            # 使用增强错误处理器，保留完整错误上下文，避免丢失定位信息
            error_info = self.error_handler.handle_error(
                e,
                context={'operation': 'render', 'content_length': len(markdown_content) if markdown_content else 0},
                recovery_strategy=ErrorRecoveryStrategy.FALLBACK
            )

            self.logger.error(f"渲染失败: {e}")
            error_result = self._render_error_result("渲染失败", str(e))
            # 追加结构化错误信息供上层透传/落盘
            try:
                error_result['error_info'] = error_info.to_dict()
            except Exception:
                pass

            # 调试落盘：记录 fail.json，便于定位“只能跳一次”问题
            try:
                import json
                debug_dir = Path(__file__).parent.parent / 'debug_render'
                debug_dir.mkdir(parents=True, exist_ok=True)
                debug_file = debug_dir / 'content_render.fail.json'
                with builtins.open(debug_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        'stage': 'render(content)',
                        'error': error_result.get('error_info', {}),
                        'message': str(e)
                    }, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
            return error_result
    
    def render_file(self, file_path: Union[str, Path], options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        渲染Markdown文件（重构：使用file_resolver统一路径解析）
        
        Args:
            file_path: 文件路径
            options: 渲染选项
            
        Returns:
            渲染结果字典
        """
        start_time = time.time()
        
        try:
            # 使用file_resolver统一路径解析
            resolve_options = {
                'max_size': self.default_options.get('max_content_length', 5 * 1024 * 1024),
                'read_content': True,  # 渲染需要读取文件内容
                'detect_encoding': True
            }
            
            # 解析文件路径
            resolve_result = self.file_resolver.resolve_file_path(file_path, resolve_options)
            
            if not resolve_result['success']:
                return self._render_error_result(
                    resolve_result['error_type'],
                    resolve_result['error_message']
                )
            
            # 获取文件内容
            content = resolve_result.get('content')
            if content is None:
                return self._render_error_result(
                    "文件读取失败",
                    "无法读取文件内容"
                )
            
            # 监控文件变化，用于缓存失效
            file_path = resolve_result['file_path']
            self.invalidation_manager.watch_file(file_path)
            
            # 渲染内容
            render_result = self.render(content, options)
            
            # 合并结果
            result = {
                **render_result,
                'file_path': resolve_result['file_path'],
                'file_info': resolve_result.get('file_info', {}),
                'encoding': resolve_result.get('encoding', {}),
                'total_time': time.time() - start_time
            }
            
            return result
            
        except Exception as e:
            # 使用增强错误处理器，保留完整错误上下文
            error_info = self.error_handler.handle_error(
                e,
                context={'operation': 'render_file', 'file_path': str(file_path)},
                recovery_strategy=ErrorRecoveryStrategy.FALLBACK
            )

            self.logger.error(f"文件渲染失败: {e}")
            error_result = self._render_error_result("文件渲染失败", str(e))
            try:
                error_result['error_info'] = error_info.to_dict()
            except Exception:
                pass

            # 调试落盘：记录 fail.json（以文件名区分）
            try:
                import json
                debug_dir = Path(__file__).parent.parent / 'debug_render'
                debug_dir.mkdir(parents=True, exist_ok=True)
                name = Path(str(file_path)).name if file_path else 'unknown.md'
                debug_file = debug_dir / f'{name}.fail.json'
                with builtins.open(debug_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        'stage': 'render_file',
                        'file_path': str(file_path),
                        'error': error_result.get('error_info', {}),
                        'message': str(e)
                    }, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
            return error_result
    
    def _render_content(self, content: str, options: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行实际的渲染操作（混合架构优先级渲染链）- 优化版本：根据used_fallback状态选择渲染策略
        
        Args:
            content: Markdown内容
            options: 渲染选项
            
        Returns:
            渲染结果
        """
        # 优化1: 根据used_fallback状态选择渲染策略
        import_result = getattr(self, '_import_result_details', {})
        used_fallback = import_result.get('used_fallback', False)
        module_name = import_result.get('module', 'unknown')
        
        # 优先级1: 使用动态导入的markdown_processor（仅当非fallback且成功时）
        if (getattr(self, 'markdown_processor_available', False) and 
            self.default_options.get('use_dynamic_import', True) and 
            not used_fallback and module_name == 'markdown_processor'):
            
            # 记录渲染决策
            self._log_render_decision(
                'markdown_processor',
                '动态导入成功，使用专用渲染器',
                {'module': module_name, 'path': import_result.get('path', 'unknown')}
            )
            try:
                funcs = getattr(self, '_markdown_processor_functions', {}) or {}
                # 安全获取函数并校验可调用性，避免 KeyError
                if options.get('enable_zoom', True):
                    render_func = funcs.get('render_markdown_with_zoom') or funcs.get('render_markdown_to_html')
                else:
                    render_func = funcs.get('render_markdown_to_html') or funcs.get('render_markdown_with_zoom')

                if callable(render_func):
                    html_content = render_func(content)
                    return {
                        'success': True,
                        'html': html_content,
                        'renderer': 'markdown_processor',
                        'renderer_details': f"动态导入模块: {module_name}",
                        'options_used': options
                    }
                else:
                    # 记录可用keys，便于诊断
                    available_keys = list(funcs.keys()) if isinstance(funcs, dict) else []
                    self.logger.warning(f"渲染函数不可调用，可用函数: {available_keys}")
                    raise KeyError(f"render function missing or not callable, available_keys={available_keys}")
            except Exception as e:
                self.logger.warning(f"markdown_processor渲染失败: {e}")
                # 记录详细错误信息
                if hasattr(self, '_import_result_details'):
                    self.logger.warning(f"  - 模块: {self._import_result_details.get('module', 'unknown')}")
                    self.logger.warning(f"  - 路径: {self._import_result_details.get('path', 'unknown')}")
                    self.logger.warning(f"  - 错误码: {self._import_result_details.get('error_code', 'unknown')}")
        
        # 优先级2: 使用备用markdown库（当fallback或动态导入失败时）
        if self.markdown_available:
            fallback_reason = ""
            if used_fallback:
                fallback_reason = f"（fallback到{module_name}）"
            elif not getattr(self, 'markdown_processor_available', False):
                fallback_reason = "（动态导入失败）"
            
            # 记录渲染决策
            self._log_render_decision(
                'markdown_library',
                f'使用备用库渲染{fallback_reason}',
                {'module': module_name, 'fallback': used_fallback}
            )
            try:
                md = markdown.Markdown(extensions=[
                    'markdown.extensions.tables',
                    'markdown.extensions.fenced_code',
                    'markdown.extensions.codehilite',
                    'markdown.extensions.toc'
                ])
                html_content = md.convert(content)
                styled_html = self._add_basic_styles(html_content)
                
                return {
                    'success': True,
                    'html': styled_html,
                    'renderer': 'markdown_library',
                    'renderer_details': f"备用库渲染{fallback_reason}",
                    'options_used': options
                }
            except Exception as e:
                self.logger.warning(f"备用markdown库渲染失败: {e}")
        
        # 优先级3: 降级到纯文本
        if options.get('fallback_to_text', True):
            # 记录渲染决策
            self._log_render_decision(
                'text_fallback',
                '所有渲染器都失败，降级到纯文本',
                {'module': module_name, 'fallback': used_fallback}
            )
            return self._render_as_text(content, options)
        
        # 完全失败
        error_msg = "所有渲染方法都失败"
        if hasattr(self, '_import_result_details'):
            error_msg += f" - 模块状态: {self._import_result_details.get('module', 'unknown')}"
            if used_fallback:
                error_msg += f", 已尝试fallback到{module_name}"
        
        self.logger.error(error_msg)
        raise Exception(error_msg)
    
    def _render_as_text(self, content: str, options: Dict[str, Any]) -> Dict[str, Any]:
        """
        将内容渲染为纯文本HTML
        
        Args:
            content: 原始内容
            options: 渲染选项
            
        Returns:
            渲染结果
        """
        # 转义HTML字符
        import html
        escaped_content = html.escape(content)
        
        # 将换行符转换为<br>标签
        formatted_content = escaped_content.replace('\n', '<br>')
        
        html_content = f"""
        <div class="text-content">
            <style>
                .text-content {{
                    font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                    white-space: pre-wrap;
                    word-wrap: break-word;
                    line-height: 1.6;
                    padding: 16px;
                    background: #f8f9fa;
                    border: 1px solid #e9ecef;
                    border-radius: 4px;
                }}
            </style>
            {formatted_content}
        </div>
        """
        
        return {
            'success': True,
            'html': html_content,
            'renderer': 'text_fallback',
            'renderer_details': '纯文本降级渲染',
            'options_used': options
        }
    
    def _log_render_decision(self, renderer_type: str, reason: str, details: Dict[str, Any] = None):
        """
        记录渲染决策过程 - 新增方法：增强日志记录
        
        Args:
            renderer_type: 选择的渲染器类型
            reason: 选择原因
            details: 详细信息
        """
        self.logger.info(f"渲染决策: 选择{renderer_type}")
        self.logger.info(f"  - 选择原因: {reason}")
        
        if details:
            for key, value in details.items():
                self.logger.info(f"  - {key}: {value}")
        
        # 记录导入状态信息
        if hasattr(self, '_import_result_details'):
            import_info = self._import_result_details
            self.logger.info(f"  - 模块状态: {import_info.get('module', 'unknown')}")
            self.logger.info(f"  - 是否fallback: {import_info.get('used_fallback', False)}")
            if import_info.get('used_fallback'):
                self.logger.info(f"  - Fallback原因: {import_info.get('fallback_reason', '未知')}")
            if import_info.get('path'):
                self.logger.info(f"  - 模块路径: {import_info.get('path')}")

        snapshot_manager = getattr(self, "snapshot_manager", None)
        if snapshot_manager:
            try:
                module_snapshot = {}
                if self.module_importer:
                    module_snapshot = self.module_importer.get_last_import_snapshot()
                snapshot_manager.save_render_snapshot({
                    "renderer_type": renderer_type,
                    "reason": reason,
                    "details": details or {},
                    "module": module_snapshot.get("module"),
                    "correlation_id": module_snapshot.get("correlation_id", ""),
                })
            except Exception:
                pass

    @staticmethod
    def get_last_render_snapshot() -> Dict[str, Any]:
        """从渲染器缓存读取最近一次渲染快照（非致命）。"""
        try:
            from pathlib import Path
            from .unified_cache_manager import UnifiedCacheManager, CacheStrategy
            cache_dir = Path(__file__).parent.parent / "cache" / "renderer"
            cm = UnifiedCacheManager(max_size=10, default_ttl=3600, strategy=CacheStrategy.LRU, cache_dir=cache_dir)
            snap = cm.get('last_render_snapshot')
            if snap:
                return snap
            # 水合最近备份（最多找3个）
            candidates = sorted(cache_dir.glob('cache_backup_*.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:3]
            for c in candidates:
                try:
                    if cm.load_from_disk(c.name):
                        snap = cm.get('last_render_snapshot')
                        if snap:
                            return snap
                except Exception:
                    continue
            return {}
        except Exception:
            return {}
    
    def _add_basic_styles(self, html_content: str) -> str:
        """
        为HTML内容添加基本样式
        
        Args:
            html_content: 原始HTML内容
            
        Returns:
            带样式的HTML内容
        """
        styles = """
        <style>
            body { font-family: '微软雅黑', 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; }
            h1, h2, h3, h4, h5, h6 { margin-top: 24px; margin-bottom: 16px; font-weight: 600; line-height: 1.25; }
            p { margin-bottom: 16px; }
            code { background: #f6f8fa; padding: 2px 4px; border-radius: 3px; font-family: 'Consolas', 'Monaco', 'Courier New', monospace; }
            pre { background: #f6f8fa; padding: 16px; border-radius: 6px; overflow: auto; margin-bottom: 16px; }
            table { border-collapse: collapse; width: 100%; margin-bottom: 16px; }
            th, td { border: 1px solid #d0d7de; padding: 8px 12px; text-align: left; }
            th { background: #f6f8fa; font-weight: 600; }
            blockquote { border-left: 4px solid #d0d7de; padding-left: 16px; margin: 16px 0; color: #656d76; }
        </style>
        """
        
        return f"{styles}\n{html_content}"
    
    def _generate_cache_key(self, content: str, options: Dict[str, Any]) -> str:
        """
        生成缓存键
        
        Args:
            content: 内容
            options: 选项
            
        Returns:
            缓存键
        """
        # 创建包含内容和选项的字符串
        cache_string = f"{content}:{str(sorted(options.items()))}"
        return hashlib.md5(cache_string.encode('utf-8')).hexdigest()
    
    def _cache_result(self, cache_key: str, result: Dict[str, Any]):
        """
        缓存渲染结果
        
        Args:
            cache_key: 缓存键
            result: 渲染结果
        """
        if len(self._render_cache) >= self._cache_max_size:
            # 移除最旧的缓存项
            oldest_key = next(iter(self._render_cache))
            del self._render_cache[oldest_key]
        
        self._render_cache[cache_key] = result.copy()
    
    def _render_error_result(self, error_type: str, error_message: str) -> Dict[str, Any]:
        """
        生成错误结果
        
        Args:
            error_type: 错误类型
            error_message: 错误消息
            
        Returns:
            错误结果字典
        """
        return {
            'success': False,
            'error_type': error_type,
            'error_message': error_message,
            'html': f"""
            <div class="error-content">
                <style>
                    .error-content {{
                        padding: 20px;
                        background: #fff3cd;
                        border: 1px solid #ffeaa7;
                        border-radius: 4px;
                        color: #856404;
                    }}
                    .error-title {{
                        font-weight: bold;
                        margin-bottom: 10px;
                    }}
                </style>
                <div class="error-title">渲染错误: {error_type}</div>
                <div>{error_message}</div>
            </div>
            """,
            'renderer': 'error_handler'
        }
    
    def clear_cache(self):
        """清空渲染缓存"""
        # 清空统一缓存管理器
        self.cache_manager.clear()
        
        # 清空失效历史
        self.invalidation_manager.invalidation_history.clear()
        
        # 兼容性：清空旧缓存
        self._render_cache.clear()
        self.logger.info("渲染缓存已清空")
    
    def get_cache_info(self) -> Dict[str, Any]:
        """获取缓存信息（统一接口）"""
        # 获取统一缓存管理器统计信息
        unified_stats = self.cache_manager.get_stats()
        
        # 获取失效管理器统计信息
        invalidation_stats = self.invalidation_manager.get_invalidation_stats()
        
        # 获取错误统计信息
        error_stats = self.error_handler.get_error_stats()
        
        return {
            'total': unified_stats.total_entries,
            'limit': unified_stats.max_size,
            'cache_size': unified_stats.total_size,  # 兼容旧字段
            'max_size': unified_stats.max_size,      # 兼容旧字段
            'cache_keys': self.cache_manager.get_keys(),
            'hit_rate': unified_stats.hit_rate,
            'hit_count': unified_stats.hit_count,
            'miss_count': unified_stats.miss_count,
            'eviction_count': unified_stats.eviction_count,
            'memory_usage_mb': unified_stats.memory_usage,
            'strategy': self.cache_manager.strategy.value,
            'legacy_cache_size': len(self._render_cache),  # 旧缓存大小
            'invalidation_stats': invalidation_stats,
            'watched_files': len(self.invalidation_manager.file_watchers),
            'error_stats': error_stats.to_dict()
        }
    
    def is_available(self) -> bool:
        """
        检查渲染器是否可用
        
        Returns:
            是否可用
        """
        return (getattr(self, 'markdown_processor_available', False) or 
                self.markdown_available)
    
    def get_supported_features(self) -> Dict[str, bool]:
        """
        获取支持的功能列表
        
        Returns:
            功能支持情况字典
        """
        return {
            'markdown_processor': getattr(self, 'markdown_processor_available', False),
            'markdown_library': self.markdown_available,
            'syntax_highlight': self.markdown_available,
            'text_fallback': True,
            'unified_path_resolution': True,
            'dynamic_module_import': getattr(self, 'markdown_processor_available', False),
            'zoom_support': getattr(self, 'markdown_processor_available', False),
            'enhanced_error_handling': True,
            'unified_caching': True,
            'cache_invalidation': True
        }
    
    def get_error_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        获取错误历史
        
        Args:
            limit: 返回数量限制
            
        Returns:
            错误历史列表
        """
        return self.error_handler.get_error_history(limit)
    
    def save_error_report(self, filename: Optional[str] = None) -> bool:
        """
        保存错误报告
        
        Args:
            filename: 文件名
            
        Returns:
            是否保存成功
        """
        return self.error_handler.save_error_report(filename)
    
    def shutdown(self):
        """关闭渲染器，释放所有资源"""
        try:
            # 关闭错误处理器
            if hasattr(self, 'error_handler'):
                self.error_handler.shutdown()
            
            # 关闭缓存失效管理器
            if hasattr(self, 'invalidation_manager'):
                self.invalidation_manager.shutdown()
            
            # 关闭统一缓存管理器
            if hasattr(self, 'cache_manager'):
                self.cache_manager.shutdown()
            
            # 关闭动态模块导入器
            if hasattr(self, 'module_importer'):
                self.module_importer.clear_cache()
            
            self.logger.info("Markdown渲染器已关闭，所有资源已释放")
            
        except Exception as e:
            self.logger.error(f"关闭渲染器时出现错误: {e}")
    
    def __del__(self):
        """析构函数，确保资源被释放"""
        try:
            self.shutdown()
        except:
            pass  # 析构函数中忽略异常
    
# 向后兼容性：保留原类名作为别名
MarkdownRenderer = HybridMarkdownRenderer

# --- 文档注释：引用示例（仅供参考，非运行代码） ---
# 统一异常与通配删除工具的示例用法：
# from core.errors import FileReadError, ServiceNotFoundError, ErrorSeverity
# from cache.delete_pattern_utils import delete_pattern
# 
# 示例：在渲染前读取文件，捕获统一文件读取异常
# try:
# 	content = file_resolver.read_file(markdown_path)
# except FileReadError as e:
# 	logger.error(f"Read failed: {e}")
# 
# 示例：当需要失效与渲染相关的解析缓存时（缓存实现无 delete_pattern）
# removed = delete_pattern(resolution_cache, "link_resolution:abc123:*")
# logger.info(f"Invalidated {removed} resolution keys")