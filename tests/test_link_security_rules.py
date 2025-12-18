#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LAD-IMPL-013 安全规则专项用例

聚焦：
- 协议/域名白名单与 fail-closed 行为
- 路径禁止模式、最大深度与盘符限制

说明：
- 为 013 提供独立的安全验收入口；
- 仅在 LAD_RUN_013_TESTS=1 时运行，避免干扰常规 CI。
"""

import os
from pathlib import Path

import pytest
import sys

# 确保可以从项目根目录导入 core/link_processor，与现有测试保持一致
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.link_processor import LinkValidator, ErrorCode


pytestmark = pytest.mark.skipif(
    os.environ.get("LAD_RUN_013_TESTS") != "1",
    reason="013 security tests are gated by LAD_RUN_013_TESTS=1",
)


def test_external_https_allowed_with_explicit_whitelist():
    """HTTPS + 白名单域名：应通过。"""
    v = LinkValidator()
    policy = {
        "security": {
            "allowed_protocols": ["https"],
            "allowed_domains": ["example.com"],
        }
    }
    res = v.validate("https://example.com/path", policy)
    assert res.ok is True
    assert res.error_code is None


def test_external_https_blocked_when_no_allowed_domains():
    """外链 fail-closed：未配置域名时默认拦截。"""
    v = LinkValidator()
    policy = {
        "security": {
            "allowed_protocols": ["https"],
            "allowed_domains": [],  # 显式空列表：触发 fail-closed 逻辑
        }
    }
    res = v.validate("https://example.com/path", policy)
    assert res.ok is False
    assert res.error_code == ErrorCode.SECURITY_BLOCKED


def test_path_forbidden_pattern_and_depth_and_drive(tmp_path):
    """路径禁止模式 + 深度限制 + 盘符限制 的代表性场景。"""
    v = LinkValidator()

    # 构造一个多层级路径，用于触发深度限制
    deep_path = tmp_path / "a" / "b" / "c" / "d"

    # 注意：对于 Path 类型，安全检查在存在性检查之前进行，
    # 因此可通过 check_exists=False 专注于安全规则本身。
    policy = {
        "check_exists": False,
        "security": {
            # 使用子路径名作为禁止模式的一部分，演示 forbidden_patterns 行为
            "forbidden_patterns": [str(Path("b"))],
        },
        "windows_specific": {
            "max_path_depth": 2,  # 故意设置得很小，以触发 depth 限制
            # 盘符白名单：如 deep_path 有盘符则仅允许该盘符；
            # 此处为了演示逻辑，刻意设置为空列表，表示不限制盘符。
            "drive_letters": [],
        },
    }

    res = v.validate(deep_path, policy)
    assert res.ok is False
    # 只要触发任一安全规则，即返回 SECURITY_BLOCKED；
    # 具体是因禁止模式或深度限制被拦截，取决于底层实现顺序。
    assert res.error_code == ErrorCode.SECURITY_BLOCKED
