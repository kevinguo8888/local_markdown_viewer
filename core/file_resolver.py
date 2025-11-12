#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件解析器模块 v1.1.0
负责文件类型识别、路径解析和编码检测
新增统一路径解析功能

作者: LAD Team
创建时间: 2025-08-02
最后更新: 2025-08-08
"""

import os
import mimetypes
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, Union
import json
from collections import OrderedDict
import ctypes
from ctypes import wintypes

try:
    import chardet
    CHARDET_AVAILABLE = True
except ImportError:
    CHARDET_AVAILABLE = False
    logging.warning("chardet库未安装，将使用基本编码检测方法")

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.config_manager import ConfigManager


class FileResolver:
    """
    文件解析器类
    提供文件类型分析、路径解析和编码检测功能
    新增统一路径解析功能，整合所有路径解析逻辑
    """
    
    # 预定义的错误类型
    ERROR_TYPES = {
        'FILE_NOT_FOUND': '文件不存在',
        'FILE_TOO_LARGE': '文件过大',
        'FILE_NOT_READABLE': '文件不可读',
        'FILE_IS_DIRECTORY': '路径是目录而非文件',
        'ENCODING_DETECTION_FAILED': '编码检测失败',
        'CONTENT_READ_FAILED': '文件内容读取失败',
        'INVALID_PATH': '无效的文件路径',
        'PERMISSION_DENIED': '权限不足',
        'UNKNOWN_ERROR': '未知错误'
    }
    
    # 默认解析选项
    DEFAULT_RESOLVE_OPTIONS = {
        'max_size': 100 * 1024 * 1024,  # 100MB
        'validate_type': True,            # 验证文件类型
        'detect_encoding': True,          # 检测编码
        'read_content': False,            # 不读取内容（默认）
        'encoding_priority': [            # 编码检测优先级
            'utf-8', 'gbk', 'gb2312', 'latin-1', 'cp1252'
        ],
        'enable_logging': True,           # 启用日志记录
        'cache_enabled': True             # 启用缓存
    }
    
    def __init__(self, config_manager: Optional[ConfigManager] = None):
        """
        初始化文件解析器
        
        Args:
            config_manager: 配置管理器实例，如果为None则创建新实例
        """
        self.config_manager = config_manager or ConfigManager()
        self.logger = logging.getLogger(__name__)
        
        # 加载文件类型配置
        self.file_types_config = self.config_manager.load_file_types_config()
        
        # 初始化MIME类型映射
        mimetypes.init()
        
        # 文件头签名映射
        self.file_signatures = {
            b'\x89PNG\r\n\x1a\n': 'image/png',
            b'\xff\xd8\xff': 'image/jpeg',
            b'GIF87a': 'image/gif',
            b'GIF89a': 'image/gif',
            b'BM': 'image/bmp',
            b'PK\x03\x04': 'application/zip',
            b'PK\x05\x06': 'application/zip',
            b'PK\x07\x08': 'application/zip',
            b'\x1f\x8b\x08': 'application/gzip',
            b'BZh': 'application/bzip2',
            b'\x37\x7A\xBC\xAF': 'application/x-7z-compressed',
            b'%PDF': 'application/pdf',
            b'<!DOCTYPE': 'text/html',
            b'<?xml': 'application/xml',
            b'{\n': 'application/json',
            b'{\r\n': 'application/json',
            b'#!': 'text/script',
        }
        self._cache: Dict[str, Dict[str, Any]] = OrderedDict()

        # 编码缓存，减少重复检测
        self._encoding_cache: Dict[str, Dict[str, Any]] = {}
    
    def is_available(self) -> bool:
        """用于测试/监控：当前解析器是否具备关键依赖。"""
        return True

    def resolve_file_path(self, file_path: Union[str, Path], options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        统一文件路径解析方法
        
        Args:
            file_path: 文件路径
            options: 解析选项
            
        Returns:
            解析结果字典
        """
        try:
            # 标准化路径
            file_path = Path(file_path).resolve()
            
            # 合并选项
            merged_options = self._merge_resolve_options(options)
            
            # 验证路径
            validation_result = self._validate_path_with_options(file_path, merged_options)
            if not validation_result['valid']:
                return self._create_error_result(
                    validation_result['error_type'],
                    validation_result['error_message'],
                    str(file_path)
                )
            
            # 获取文件信息
            file_info = self._get_file_info(file_path)
            if 'error' in file_info:
                return self._create_error_result(
                    'FILE_INFO_ERROR',
                    file_info['error'],
                    str(file_path)
                )
            
            # 分析文件类型
            file_type = self._analyze_file_type(file_path)
            if 'error' in file_type:
                return self._create_error_result(
                    'FILE_TYPE_ERROR',
                    file_type['error'],
                    str(file_path)
                )
            
            # 检测编码
            encoding_info = None
            if merged_options.get('detect_encoding', True):
                encoding_info = self._detect_encoding(file_path)
            
            # 读取文件内容（如果需要）
            content = None
            if merged_options.get('read_content', False):
                content_result = self._read_file_content_with_encoding(file_path, encoding_info, merged_options)
                if content_result['success']:
                    content = content_result['content']
                    encoding_info = {'encoding': content_result['encoding']}
                else:
                    return self._create_error_result(
                        'CONTENT_READ_FAILED',
                        content_result['error'],
                        str(file_path)
                    )
            
            # 构建成功结果
            result = {
                'success': True,
                'file_path': self._normalize_path(file_path),
                'file_info': file_info,
                'file_type': file_type,
                'encoding': encoding_info or {},
                'resolved_at': self._get_timestamp()
            }
            
            if content is not None:
                result['content'] = content
            
            return result
            
        except Exception as e:
            self.logger.error(f"文件路径解析失败: {e}")
            return self._create_error_result(
                'UNKNOWN_ERROR',
                f"文件路径解析失败: {e}",
                str(file_path) if 'file_path' in locals() else str(file_path)
            )

    def _merge_resolve_options(self, options: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """合并用户选项和默认选项"""
        if options is None:
            return self.DEFAULT_RESOLVE_OPTIONS.copy()
        
        merged_options = self.DEFAULT_RESOLVE_OPTIONS.copy()
        merged_options.update(options)
        return merged_options
    
    def _normalize_path(self, file_path: Path) -> str:
        try:
            # Windows 返回长路径（避免 RUNNER~1），其他平台返回规范化字符串
            if os.name == 'nt':
                return self._normalize_path_windows(file_path)
            return os.path.normpath(str(file_path))
        except Exception:
            return str(file_path)

    def _normalize_path_windows(self, file_path: Path) -> str:
        try:
            p = str(file_path)
            GetLongPathNameW = ctypes.windll.kernel32.GetLongPathNameW
            GetLongPathNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
            GetLongPathNameW.restype = wintypes.DWORD
            buf_len = 260
            while True:
                buf = ctypes.create_unicode_buffer(buf_len)
                r = GetLongPathNameW(p, buf, buf_len)
                if r == 0:
                    break
                if r > buf_len:
                    buf_len = r
                    continue
                p = buf.value
                break
            return os.path.normpath(p)
        except Exception:
            return os.path.normpath(str(file_path))
    
    def _validate_path_with_options(self, file_path: Path, options: Dict[str, Any]) -> Dict[str, Any]:
        """使用选项验证文件路径"""
        try:
            # 检查路径是否存在
            if not file_path.exists():
                return {
                    'valid': False,
                    'error_type': 'FILE_NOT_FOUND',
                    'error_message': f"文件不存在: {file_path}"
                }
            
            # 检查是否为文件
            if not file_path.is_file():
                return {
                    'valid': False,
                    'error_type': 'FILE_IS_DIRECTORY',
                    'error_message': f"路径是目录而非文件: {file_path}"
                }
            
            # 检查文件大小
            file_size = file_path.stat().st_size
            max_size = options.get('max_size', self.DEFAULT_RESOLVE_OPTIONS['max_size'])
            
            if file_size > max_size:
                return {
                    'valid': False,
                    'error_type': 'FILE_TOO_LARGE',
                    'error_message': f"文件过大: {file_path} ({self._format_file_size(file_size)})"
                }
            
            # 检查文件权限
            if not os.access(file_path, os.R_OK):
                return {
                    'valid': False,
                    'error_type': 'PERMISSION_DENIED',
                    'error_message': f"权限不足，无法访问: {file_path}"
                }
            
            return {'valid': True}
            
        except Exception as e:
            return {
                'valid': False,
                'error_type': 'UNKNOWN_ERROR',
                'error_message': f"路径验证失败: {e}"
            }
    
    def _read_file_content_with_encoding(
        self, 
        file_path: Path, 
        encoding_info: Optional[Dict[str, Any]], 
        options: Dict[str, Any]
    ) -> Dict[str, Any]:
        """使用编码信息读取文件内容"""
        try:
            # 如果已有编码信息，直接使用
            type_options = self._get_file_type_options(file_path)
            type_encoding = type_options.get('encoding') if type_options else None

            if not encoding_info or not encoding_info.get('encoding'):
                cached = self._encoding_cache.get(str(file_path))
                if cached:
                    encoding_info = cached
                elif type_encoding:
                    encoding_info = {
                        'encoding': type_encoding,
                        'confidence': 1.0,
                        'method': 'type_config'
                    }
                    self._encoding_cache[str(file_path)] = encoding_info

            if encoding_info and encoding_info.get('encoding'):
                try:
                    with open(file_path, 'r', encoding=encoding_info['encoding']) as f:
                        content = f.read()
                    self._encoding_cache[str(file_path)] = encoding_info
                    return {
                        'success': True,
                        'content': content,
                        'encoding': encoding_info['encoding']
                    }
                except UnicodeDecodeError:
                    self.logger.warning(f"使用检测到的编码读取失败，尝试其他编码")
                    self._encoding_cache.pop(str(file_path), None)

            encodings = options.get('encoding_priority', self.DEFAULT_RESOLVE_OPTIONS['encoding_priority'])
            if type_encoding and type_encoding not in encodings:
                encodings = [type_encoding] + encodings

            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        content = f.read()
                    self._encoding_cache[str(file_path)] = {'encoding': encoding, 'method': 'priority'}
                    return {
                        'success': True,
                        'content': content,
                        'encoding': encoding
                    }
                except UnicodeDecodeError:
                    continue
                except Exception as e:
                    self.logger.debug(f"编码{encoding}读取失败: {e}")
                    continue
            
            if type_encoding:
                try:
                    with open(file_path, 'r', encoding=type_encoding, errors='replace') as f:
                        content = f.read()
                    self._encoding_cache[str(file_path)] = {'encoding': type_encoding, 'method': 'fallback'}
                    return {
                        'success': True,
                        'content': content,
                        'encoding': type_encoding
                    }
                except Exception:
                    pass

            return {
                'success': False,
                'error': '所有编码尝试都失败'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f"文件读取失败: {e}"
            }
    
    def _create_error_result(self, error_type: str, error_message: str, file_path: str) -> Dict[str, Any]:
        """创建错误结果"""
        return {
            'success': False,
            'error_type': error_type,
            'error_message': error_message,
            'file_path': file_path,
            'resolved_at': self._get_timestamp()
        }
    

    
    def _get_file_info(self, file_path: Path) -> Dict[str, Any]:
        """
        获取文件基本信息
        
        Args:
            file_path: 文件路径
            
        Returns:
            文件信息字典
        """
        try:
            stat = file_path.stat()
            
            return {
                'name': file_path.name,
                'extension': file_path.suffix.lower(),
                'size': stat.st_size,
                'size_formatted': self._format_file_size(stat.st_size),
                'modified_time': stat.st_mtime,
                'created_time': stat.st_ctime,
                'is_readable': os.access(file_path, os.R_OK),
                'is_writable': os.access(file_path, os.W_OK),
                'is_executable': os.access(file_path, os.X_OK)
            }
            
        except Exception as e:
            self.logger.error(f"获取文件信息失败: {e}")
            return {'error': str(e)}
    
    def _analyze_file_type(self, file_path: Path) -> Dict[str, Any]:
        """
        分析文件类型
        
        Args:
            file_path: 文件路径
            
        Returns:
            文件类型信息字典
        """
        try:
            extension = file_path.suffix.lower()
            
            # 1. 基于扩展名的类型识别
            extension_type = self._get_type_by_extension(extension)
            
            # 2. 基于MIME类型的识别
            mime_type = mimetypes.guess_type(str(file_path))[0]
            
            # 3. 基于文件头的识别
            header_type = self._get_type_by_header(file_path)
            
            # 4. 确定最终类型
            final_type = self._determine_final_type(extension_type, mime_type, header_type)
            
            return {
                'extension': extension,
                'extension_type': extension_type,
                'mime_type': mime_type,
                'header_type': header_type,
                'final_type': final_type,
                'confidence': self._calculate_confidence(extension_type, mime_type, header_type)
            }
            
        except Exception as e:
            self.logger.error(f"文件类型分析失败: {e}")
            return {'error': str(e)}
    
    def _get_type_by_extension(self, extension: str) -> Optional[Dict[str, Any]]:
        """
        基于扩展名获取文件类型信息
        
        Args:
            extension: 文件扩展名
            
        Returns:
            文件类型信息字典
        """
        self.file_types_config = self.config_manager.load_file_types_config()
        fallback_type = None
        for type_name, type_info in self.file_types_config.items():
            if type_info.get('include_else') and fallback_type is None:
                fallback_type = {
                    'name': type_name,
                    'renderer': type_info.get('renderer'),
                    'preview_mode': type_info.get('preview_mode'),
                    'icon': type_info.get('icon'),
                    'description': type_info.get('description'),
                    'encoding': type_info.get('encoding')
                }
            if extension in type_info.get('extensions', []):
                return {
                    'name': type_name,
                    'renderer': type_info.get('renderer'),
                    'preview_mode': type_info.get('preview_mode'),
                    'icon': type_info.get('icon'),
                    'description': type_info.get('description'),
                    'encoding': type_info.get('encoding')
                }
        return fallback_type

    def _get_file_type_options(self, file_path: Path) -> Dict[str, Any]:
        """获取文件类型配置详情（含编码等扩展参数）。"""
        extension = file_path.suffix.lower()
        self.file_types_config = self.config_manager.load_file_types_config()
        for _, type_info in self.file_types_config.items():
            if extension in type_info.get('extensions', []):
                return type_info
        for type_name, type_info in self.file_types_config.items():
            if type_info.get('include_else'):
                return type_info
        return {}
    
    def _get_type_by_header(self, file_path: Path) -> Optional[str]:
        """
        基于文件头获取文件类型
        
        Args:
            file_path: 文件路径
            
        Returns:
            MIME类型字符串
        """
        try:
            with open(file_path, 'rb') as f:
                header = f.read(16)  # 读取前16字节
                
                for signature, mime_type in self.file_signatures.items():
                    if header.startswith(signature):
                        return mime_type
                        
        except Exception as e:
            self.logger.debug(f"文件头分析失败: {e}")
            
        return None
    
    def _determine_final_type(self, extension_type: Optional[Dict], 
                            mime_type: Optional[str], 
                            header_type: Optional[str]) -> str:
        """
        确定最终的文件类型
        
        Args:
            extension_type: 扩展名类型信息
            mime_type: MIME类型
            header_type: 文件头类型
            
        Returns:
            最终确定的类型
        """
        # 优先级：扩展名 > 文件头 > MIME类型
        if extension_type:
            return extension_type['name']
        elif header_type:
            return header_type
        elif mime_type:
            return mime_type
        else:
            return 'unknown'
    
    def _calculate_confidence(self, extension_type: Optional[Dict], 
                            mime_type: Optional[str], 
                            header_type: Optional[str]) -> float:
        """
        计算类型识别的置信度
        
        Args:
            extension_type: 扩展名类型信息
            mime_type: MIME类型
            header_type: 文件头类型
            
        Returns:
            置信度（0.0-1.0）
        """
        confidence = 0.0
        
        if extension_type:
            confidence += 0.5
        if mime_type:
            confidence += 0.3
        if header_type:
            confidence += 0.2
            
        return min(confidence, 1.0)
    
    def _detect_encoding(self, file_path: Path) -> Dict[str, Any]:
        """
        检测文件编码
        
        Args:
            file_path: 文件路径
            
        Returns:
            编码信息字典
        """
        try:
            # 尝试使用chardet检测编码
            if CHARDET_AVAILABLE:
                return self._detect_encoding_with_chardet(file_path)
            else:
                return self._detect_encoding_basic(file_path)
                
        except Exception as e:
            self.logger.error(f"编码检测失败: {e}")
            return {
                'encoding': 'unknown',
                'confidence': 0.0,
                'error': str(e)
            }
    
    def _detect_encoding_with_chardet(self, file_path: Path) -> Dict[str, Any]:
        """
        使用chardet库检测编码
        
        Args:
            file_path: 文件路径
            
        Returns:
            编码信息字典
        """
        try:
            with open(file_path, 'rb') as f:
                raw_data = f.read(1024 * 1024)  # 读取1MB用于检测
                
            result = chardet.detect(raw_data)
            
            return {
                'encoding': result['encoding'],
                'confidence': result['confidence'],
                'method': 'chardet'
            }
            
        except Exception as e:
            self.logger.error(f"chardet编码检测失败: {e}")
            return self._detect_encoding_basic(file_path)
    
    def _detect_encoding_basic(self, file_path: Path) -> Dict[str, Any]:
        """
        基本编码检测方法
        
        Args:
            file_path: 文件路径
            
        Returns:
            编码信息字典
        """
        encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1', 'cp1252']
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    f.read(1024)  # 尝试读取一小部分
                return {
                    'encoding': encoding,
                    'confidence': 0.8,
                    'method': 'basic'
                }
            except UnicodeDecodeError:
                continue
            except Exception as e:
                self.logger.debug(f"编码{encoding}检测失败: {e}")
                continue
        
        return {
            'encoding': 'unknown',
            'confidence': 0.0,
            'method': 'basic'
        }
    
    def _format_file_size(self, size_bytes: int) -> str:
        """
        格式化文件大小
        
        Args:
            size_bytes: 文件大小（字节）
            
        Returns:
            格式化的文件大小字符串
        """
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        
        return f"{size_bytes:.1f} {size_names[i]}"
    
    def _get_timestamp(self) -> str:
        """
        获取当前时间戳
        
        Returns:
            时间戳字符串
        """
        from datetime import datetime
        return datetime.now().isoformat()
    
    def get_supported_extensions(self) -> Dict[str, list]:
        """
        获取支持的文件扩展名列表
        
        Returns:
            文件类型到扩展名的映射
        """
        result = {}
        for type_name, type_info in self.file_types_config.items():
            result[type_name] = type_info.get('extensions', [])
        return result
    
    def get_supported_encodings(self) -> list:
        """
        获取支持的编码列表
        
        Returns:
            支持的编码列表
        """
        return ['utf-8', 'gbk', 'gb2312', 'latin-1', 'cp1252', 'ascii']
    
    def is_supported_file(self, file_path: Union[str, Path]) -> bool:
        """
        检查文件是否被支持
        
        Args:
            file_path: 文件路径
            
        Returns:
            是否支持该文件
        """
        try:
            file_path = Path(file_path)
            extension = file_path.suffix.lower()
            
            for type_info in self.file_types_config.values():
                if extension in type_info.get('extensions', []):
                    return True
                    
            return False
            
        except Exception as e:
            self.logger.error(f"文件支持检查失败: {e}")
            return False
            



            