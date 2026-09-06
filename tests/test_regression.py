# -*- coding: utf-8 -*-
"""
回归测试：覆盖代码审查发现的 Critical / Required 修复。

运行方式（项目根目录）：
    python -m unittest discover -s tests -t . -v

纯逻辑用例仅依赖标准库；需要 GitPython 的用例在完整项目环境中自动执行，
缺少 GitPython 时跳过（不会误报失败）。
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

GITPYTHON_AVAILABLE = importlib.util.find_spec("git") is not None
FULL_DEPS_AVAILABLE = all(
    importlib.util.find_spec(name) is not None for name in ("git", "github", "dotenv")
)
AI_DEPS_AVAILABLE = all(
    importlib.util.find_spec(name) is not None for name in ("openai", "dotenv")
)
DOTENV_AVAILABLE = importlib.util.find_spec("dotenv") is not None


class ReleaseTabRegressionTest(unittest.TestCase):
    """Critical：自动发版预览崩溃（UI 引用了不存在的 info.tag_name）。"""

    def test_release_info_exposes_tag_field(self) -> None:
        from models import ReleaseInfo

        info = ReleaseInfo(tag="v1.2.0", changelog="changelog")
        self.assertEqual(info.tag, "v1.2.0")

    def test_release_tab_renders_tag_not_tag_name(self) -> None:
        """源码级回归护栏：tab_release 若再次出现 tag_name 会直接崩溃。"""
        source = (PROJECT_ROOT / "ui" / "tab_release.py").read_text(encoding="utf-8")
        self.assertNotIn("info.tag_name", source)


@unittest.skipUnless(FULL_DEPS_AVAILABLE, "需要 GitPython / PyGithub / python-dotenv（项目完整环境）")
class HostServiceFallbackGuardTest(unittest.TestCase):
    """Critical：hosting_service 的 AI 降级路径引用未导入的 AIEngineError。"""

    def test_hosting_service_binds_aiengine_error(self) -> None:
        """except 子句在异常发生时求值，若未导入会在降级时抛 NameError。"""
        from services import hosting_service

        self.assertTrue(hasattr(hosting_service, "AIEngineError"))

    def test_hosting_service_imports_aiengine_error(self) -> None:
        """源码级回归护栏：导入行必须包含 AIEngineError。"""
        source = (PROJECT_ROOT / "services" / "hosting_service.py").read_text(encoding="utf-8")
        self.assertIn("from core.ai_engine import AIEngine, AIEngineError", source)


class ReleaseTagSessionStateGuardTest(unittest.TestCase):
    """Critical：tab_release 对 widget 已占用的 session key 赋值导致 StreamlitAPIException。"""

    def test_release_tab_does_not_reassign_widget_key(self) -> None:
        """源码级回归护栏：key=release_full_name 的 widget 不允许再被 session_state 赋值。"""
        source = (PROJECT_ROOT / "ui" / "tab_release.py").read_text(encoding="utf-8")
        self.assertNotIn('st.session_state["release_full_name"] =', source)


class AppFooterI18nGuardTest(unittest.TestCase):
    """Required：app.py 页脚 i18n 占位符写在普通字符串中被原样渲染。"""

    def test_footer_placeholder_is_interpolated(self) -> None:
        """源码级回归护栏：页脚不得再出现字面量占位符。"""
        source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
        self.assertNotIn('{components.tr("app.footer")}', source)


@unittest.skipUnless(GITPYTHON_AVAILABLE, "需要 GitPython（项目完整环境）")
class ReleaseVersionKeyMixedTagsTest(unittest.TestCase):
    """Required：v 前缀与无前缀标签混用时 _version_key 不应抛 TypeError。"""

    def test_mixed_prefix_tags_sort_without_error(self) -> None:
        from services.release_service import _version_key

        tags = ["v1.0.0", "1.2.0", "v2.0.0", "0.9.0"]
        self.assertEqual(sorted(tags, key=_version_key)[-1], "v2.0.0")

    def test_v_prefix_digits_only_key(self) -> None:
        from services.release_service import _version_key

        self.assertEqual(_version_key("v1.10.0"), (1, 10, 0))
        self.assertEqual(_version_key("release-2"), (2,))


@unittest.skipUnless(DOTENV_AVAILABLE, "需要 python-dotenv（项目完整环境）")
class ConfigToleranceTest(unittest.TestCase):
    """Required：非法 .env 值应回退默认值并记录警告，而不是导入期崩溃。"""

    def test_bad_int_env_falls_back_with_warning(self) -> None:
        import os
        from unittest import mock

        from config import load_settings

        env = {"REQUEST_TIMEOUT": "abc", "TRENDING_TOP_N": "3.5", "EMAIL_SMTP_PORT": "not-a-port"}
        with mock.patch.dict(os.environ, env):
            settings = load_settings()
        self.assertEqual(settings.request_timeout, 30)
        self.assertEqual(settings.trending_top_n, 3)
        self.assertEqual(settings.email_smtp_port, 465)
        warnings_text = "\n".join(settings.config_warnings)
        self.assertIn("REQUEST_TIMEOUT", warnings_text)
        self.assertIn("TRENDING_TOP_N", warnings_text)
        self.assertIn("EMAIL_SMTP_PORT", warnings_text)

    def test_bad_enum_env_falls_back_with_warning(self) -> None:
        import os
        from unittest import mock

        from config import load_settings

        env = {"DEFAULT_REPO_VISIBILITY": "internal", "TRENDING_SINCE": "hourly"}
        with mock.patch.dict(os.environ, env):
            settings = load_settings()
        self.assertEqual(settings.default_repo_visibility, "private")
        self.assertEqual(settings.trending_since, "daily")
        self.assertEqual(len(settings.config_warnings), 2)

    def test_valid_env_records_no_warnings(self) -> None:
        import os
        from unittest import mock

        from config import load_settings

        env = {
            "DEFAULT_REPO_VISIBILITY": "public",
            "TRENDING_SINCE": "weekly",
            "REQUEST_TIMEOUT": "45",
            "TRENDING_TOP_N": "5",
            "AI_FALLBACK_ENABLED": "false",
        }
        with mock.patch.dict(os.environ, env):
            settings = load_settings()
        self.assertEqual(settings.request_timeout, 45)
        self.assertTrue(settings.ai_fallback_enabled is False)
        self.assertEqual(settings.config_warnings, [])


@unittest.skipUnless(AI_DEPS_AVAILABLE, "需要 openai / python-dotenv（项目完整环境）")
class AIModelRoutingTest(unittest.TestCase):
    """方案 B：COMMIT/TRENDING 场景模型覆盖 + OPENAI_FALLBACK_MODEL 降级链。"""

    def _make_engine(self):
        from core.ai_engine import AIEngine

        # 占位 key 仅判真、不发请求；短字面量避免命中密钥扫描规则
        return AIEngine(api_key="test", model="primary-model")

    def test_task_model_override(self) -> None:
        from unittest import mock

        from config import settings

        engine = self._make_engine()
        with mock.patch.object(settings, "commit_model", "fast-commit"), \
                mock.patch.object(settings, "trending_model", ""):
            self.assertEqual(engine._resolve_model("commit"), "fast-commit")
            self.assertEqual(engine._resolve_model("trending"), "primary-model")
            self.assertEqual(engine._resolve_model(None), "primary-model")

    def test_model_chain_parses_and_dedupes(self) -> None:
        from unittest import mock

        from config import settings

        engine = self._make_engine()
        with mock.patch.object(settings, "openai_fallback_model", " backup-a, ，backup-b ;;backup-a "):
            self.assertEqual(engine._model_chain(None), ["primary-model", "backup-a", "backup-b"])
        with mock.patch.object(settings, "openai_fallback_model", ""):
            self.assertEqual(engine._model_chain("commit"), ["primary-model"])

    @staticmethod
    def _openai_error(exc_cls, status: int):
        import httpx

        request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
        return exc_cls("api error", response=httpx.Response(status, request=request), body=None)

    def test_fallback_switches_on_rate_limit(self) -> None:
        from unittest import mock

        from config import settings
        from openai import RateLimitError

        engine = self._make_engine()
        calls = []

        def fake_create(**kwargs):
            calls.append(kwargs["model"])
            if len(calls) == 1:
                raise self._openai_error(RateLimitError, 429)
            return mock.Mock(choices=[mock.Mock(message=mock.Mock(content="hello"))])

        client = mock.Mock()
        client.chat.completions.create.side_effect = fake_create
        with mock.patch.object(settings, "openai_fallback_model", "backup-model"), \
                mock.patch.object(engine, "_get_client", return_value=client):
            self.assertEqual(engine._chat("sys", "usr"), "hello")
        self.assertEqual(calls, ["primary-model", "backup-model"])

    def test_auth_error_does_not_switch(self) -> None:
        from unittest import mock

        from config import settings
        from openai import AuthenticationError

        from core.ai_engine import AIEngineError

        engine = self._make_engine()
        client = mock.Mock()
        client.chat.completions.create.side_effect = self._openai_error(AuthenticationError, 401)
        with mock.patch.object(settings, "openai_fallback_model", "backup-model"), \
                mock.patch.object(engine, "_get_client", return_value=client):
            with self.assertRaises(AIEngineError):
                engine._chat("sys", "usr")
        self.assertEqual(client.chat.completions.create.call_count, 1)

    def test_raises_after_chain_exhausted(self) -> None:
        from unittest import mock

        from config import settings
        from openai import RateLimitError

        from core.ai_engine import AIEngineError

        engine = self._make_engine()
        client = mock.Mock()
        client.chat.completions.create.side_effect = self._openai_error(RateLimitError, 429)
        with mock.patch.object(settings, "openai_fallback_model", "backup-a, backup-b"), \
                mock.patch.object(engine, "_get_client", return_value=client):
            with self.assertRaises(AIEngineError):
                engine._chat("sys", "usr")
        self.assertEqual(client.chat.completions.create.call_count, 3)


class I18nParityTest(unittest.TestCase):
    """Required：中英文案键完全对齐，代码引用的键必须存在。"""

    def test_zh_en_key_parity(self) -> None:
        from core.i18n import TRANSLATIONS

        self.assertEqual(set(TRANSLATIONS["zh_CN"]), set(TRANSLATIONS["en_US"]))

    def test_referenced_keys_exist(self) -> None:
        import re

        from core.i18n import TRANSLATIONS

        ui_dir = PROJECT_ROOT / "ui"
        used = set()
        for path in list(ui_dir.rglob("*.py")) + [PROJECT_ROOT / "app.py"]:
            source = path.read_text(encoding="utf-8")
            used |= set(re.findall(r"tr\(\s*['\"]([\w.]+)['\"]", source))
        missing = sorted(k for k in used if k not in TRANSLATIONS["zh_CN"])
        self.assertEqual(missing, [], f"代码引用了不存在的文案键: {missing}")

    def test_trending_restore_entry_exists(self) -> None:
        """源码级回归护栏：Master-Detail 必须保留「移回新榜」入口。"""
        source = (PROJECT_ROOT / "ui" / "tab_trending.py").read_text(encoding="utf-8")
        self.assertIn('_set_status(repo.name, "new")', source)
        self.assertIn('tr("trending.restore")', source)


@unittest.skipUnless(AI_DEPS_AVAILABLE, "需要 openai / python-dotenv（项目完整环境）")
class TruncateTextTest(unittest.TestCase):
    """Required：截断硬切补省略号，不得在词中间无声断裂。"""

    def test_hard_cut_appends_ellipsis(self) -> None:
        from core.llm_summary import _truncate_text

        text = "确定推理引擎：支持前向链、Rete、Datalog 和 Spark 等多种推理方式"
        result = _truncate_text(text, 30)
        self.assertTrue(result.endswith("…"))
        self.assertLessEqual(len(result), 31)

    def test_short_text_unchanged(self) -> None:
        from core.llm_summary import _truncate_text

        self.assertEqual(_truncate_text("短文本", 30), "短文本")

    def test_punctuation_cut_preferred(self) -> None:
        from core.llm_summary import _truncate_text

        # 句号位于截断窗口 60% 之后：应在该句号处断句
        text = "前面是一段足够长的内容用于超过截断阈值的位置。后面还有更多内容"
        result = _truncate_text(text, 30)
        self.assertTrue(result.endswith("。"))
        self.assertFalse(result.endswith("…"))

    def test_early_punctuation_hard_cuts(self) -> None:
        from core.llm_summary import _truncate_text

        # 句号过早（<60%）：保留它会丢失过多内容，应硬切并补省略号
        text = "短。后面是很长的补充内容一直延伸到超过三十个字符限制位置为止哦"
        result = _truncate_text(text, 30)
        self.assertTrue(result.endswith("…"))


@unittest.skipUnless(FULL_DEPS_AVAILABLE, "需要 GitPython / PyGithub / python-dotenv（项目完整环境）")
class DailyPushDedupTest(unittest.TestCase):
    """Critical：托盘/桌面壳/任务计划多进程并发触发每日推送会重复发送。"""

    def test_dedup_roundtrip(self) -> None:
        import tempfile

        from core import scheduler

        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / ".last_daily_push"
            self.assertFalse(scheduler.already_pushed_today(marker))
            scheduler._mark_pushed_today(marker)
            self.assertTrue(scheduler.already_pushed_today(marker))
            # 第二天自动失效：模拟 marker 内容为昨日
            marker.write_text("2000-01-01", encoding="utf-8")
            self.assertFalse(scheduler.already_pushed_today(marker))

    def test_missing_marker_file_is_not_pushed(self) -> None:
        from core import scheduler

        self.assertFalse(scheduler.already_pushed_today(Path("Z:/nonexistent/marker")))


class EnvFileGuardTest(unittest.TestCase):
    """Required：提交前拦截未忽略的环境变量文件（纯命名过滤逻辑）。"""

    def test_detects_plain_env(self) -> None:
        from core.env_guard import is_env_file

        self.assertTrue(is_env_file(".env"))

    def test_detects_env_suffix_files(self) -> None:
        from core.env_guard import is_env_file

        self.assertTrue(is_env_file(".env.local"))
        self.assertTrue(is_env_file(".env.prod"))
        self.assertTrue(is_env_file(".env.backup"))

    def test_allows_env_example(self) -> None:
        from core.env_guard import is_env_file

        self.assertFalse(is_env_file(".env.example"))

    def test_ignores_regular_files(self) -> None:
        from core.env_guard import is_env_file

        self.assertFalse(is_env_file("app.py"))
        self.assertFalse(is_env_file("env/"))
        self.assertFalse(is_env_file("requirements.txt"))


@unittest.skipUnless(GITPYTHON_AVAILABLE, "需要 GitPython（项目完整环境）")
class UnignoredEnvFilesIntegrationTest(unittest.TestCase):
    """Required：在真实 git 仓库中识别即将被 git add -A 提交的 .env。"""

    def test_unignored_env_is_detected(self) -> None:
        import tempfile

        from git import Repo

        from core.env_guard import unignored_env_files

        with tempfile.TemporaryDirectory() as tmp:
            repo = Repo.init(tmp)
            (Path(tmp) / ".env").write_text("GITHUB_TOKEN=secret\n", encoding="utf-8")
            (Path(tmp) / "app.py").write_text("print(1)\n", encoding="utf-8")
            self.assertIn(".env", unignored_env_files(repo))

    def test_ignored_env_is_not_detected(self) -> None:
        import tempfile

        from git import Repo

        from core.env_guard import unignored_env_files

        with tempfile.TemporaryDirectory() as tmp:
            repo = Repo.init(tmp)
            (Path(tmp) / ".gitignore").write_text(".env\n", encoding="utf-8")
            (Path(tmp) / ".env").write_text("GITHUB_TOKEN=secret\n", encoding="utf-8")
            self.assertEqual(unignored_env_files(repo), [])

    def test_env_example_is_not_detected(self) -> None:
        import tempfile

        from git import Repo

        from core.env_guard import unignored_env_files

        with tempfile.TemporaryDirectory() as tmp:
            repo = Repo.init(tmp)
            (Path(tmp) / ".env.example").write_text("GITHUB_TOKEN=\n", encoding="utf-8")
            self.assertEqual(unignored_env_files(repo), [])


if __name__ == "__main__":
    unittest.main()
