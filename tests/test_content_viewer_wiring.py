from pathlib import Path
import os
import sys

# 确保在导入 content_viewer 前启用测试模式，避免在 pytest 环境初始化真实 QWebEnginePage
os.environ.setdefault("LAD_TEST_MODE", "1")

sys.path.insert(0, str(Path(__file__).parent.parent))

from ui.content_viewer import _CVPage


class _DummyOwner:
    def __init__(self):
        self.last_href = None
        self.console_messages = []

    def _on_js_console_message(self, level, message, line_number, source_id):
        self.console_messages.append((level, message, line_number, source_id))

    def _handle_lpclick(self, href: str):
        self.last_href = href


class _DummyUrl:
    def __init__(self, value: str):
        self._value = value

    def __str__(self) -> str:
        return self._value


def test_cvpage_lpclick_console_to_owner():
    owner = _DummyOwner()
    page = _CVPage(owner)
    page.javaScriptConsoleMessage(0, "LPCLICK:/foo/bar", 0, "test")
    assert owner.last_href == "/foo/bar"


def test_cvpage_accept_navigation_request_calls_owner_for_link():
    owner = _DummyOwner()
    page = _CVPage(owner)
    url = _DummyUrl("/target.md")
    result = page.acceptNavigationRequest(url, "NavigationTypeLinkClicked", True)
    assert owner.last_href == "/target.md"
    assert result is False
