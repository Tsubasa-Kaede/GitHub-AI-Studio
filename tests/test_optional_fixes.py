# -*- coding: utf-8 -*-
"""
回归测试：覆盖第二轮修复（审查 Optional 级建议）。

运行方式（项目根目录）：
    python -m unittest discover -s tests -t . -v

纯逻辑用例仅依赖标准库；依赖第三方包的用例在完整项目环境中自动执行，
缺少对应依赖时跳过（不会误报失败）。
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _has_all(*names: str) -> bool:
    return all(importlib.util.find_spec(name) is not None for name in names)


@unittest.skipUnless(
    _has_all("openai", "github", "dotenv"),
    "需要 openai / PyGithub / python-dotenv（项目完整环境）",
)
class ReleaseVersionKeyTest(unittest.TestCase):
    """语义化版本排序：v1.10 应排在 v1.9 之后。"""

    def test_v1_10_sorts_after_v1_9(self) -> None:
        from services.release_service import _version_key

        tags = ["v1.9.0", "v1.10.0", "v0.2.0"]
        self.assertEqual(sorted(tags, key=_version_key)[-1], "v1.10.0")

    def test_v_prefix_and_letters_are_tolerated(self) -> None:
        from services.release_service import _version_key

        self.assertLess(_version_key("v1.9"), _version_key("v1.10"))
        self.assertLess(_version_key("release-2"), _version_key("release-10"))


@unittest.skipUnless(_has_all("requests"), "需要 requests（项目完整环境）")
class SecurityExampleFilterTest(unittest.TestCase):
    """示例过滤收紧：只有值本身是占位符才放行。"""

    def test_real_secret_with_example_comment_is_flagged(self) -> None:
        from core.security_guard import SecurityGuard

        line = 'api_key = "sk-abc1234567890"  # example usage'
        self.assertTrue(SecurityGuard().scan_text(line))

    def test_bare_token_with_example_comment_is_flagged(self) -> None:
        from core.security_guard import SecurityGuard

        token = "ghp_" + "A" * 36
        line = f"# example: GITHUB_TOKEN={token}"
        self.assertTrue(SecurityGuard().scan_text(line))

    def test_placeholder_value_is_filtered(self) -> None:
        from core.security_guard import SecurityGuard

        line = 'api_key = "your_key_here"'
        self.assertEqual(SecurityGuard().scan_text(line), [])


@unittest.skipUnless(_has_all("requests", "dotenv"), "需要 requests / python-dotenv（项目完整环境）")
class NotifierActionParseTest(unittest.TestCase):
    """Ntfy 动作解析：标签允许包含逗号。"""

    def test_view_label_may_contain_commas(self) -> None:
        from core.ntfy_engine import NtfyEngine

        parsed = NtfyEngine._parse_actions(["view, 打开, GitHub, https://github.com/x"])
        self.assertEqual(parsed[0]["url"], "https://github.com/x")
        self.assertEqual(parsed[0]["label"], "打开, GitHub")

    def test_http_action_keeps_extra_params(self) -> None:
        from core.ntfy_engine import NtfyEngine

        parsed = NtfyEngine._parse_actions(["http, 归档, Notion, https://wb, method=POST"])
        self.assertEqual(parsed[0]["action"], "http")
        self.assertEqual(parsed[0]["label"], "归档, Notion")
        self.assertEqual(parsed[0]["url"], "https://wb")
        self.assertEqual(parsed[0]["method"], "POST")


@unittest.skipUnless(
    _has_all("requests", "dotenv", "openai", "github"),
    "需要项目完整依赖（热榜服务）",
)
class ProxyFallbackTest(unittest.TestCase):
    """代理不可达时自动去掉代理直连重试。"""

    def test_proxy_fallback_retries_without_proxy(self) -> None:
        from unittest import mock

        from requests.exceptions import ProxyError

        from services import trending_service

        calls = []

        def fake_get(url, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise ProxyError("proxy down")
            return mock.Mock()

        with mock.patch.object(trending_service.requests, "get", side_effect=fake_get):
            trending_service._get_with_proxy_fallback("https://example.com")

        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1].get("proxies"), {"http": None, "https": None})


if __name__ == "__main__":
    unittest.main()
