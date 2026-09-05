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


GITPYTHON_AVAILABLE = importlib.util.find_spec("git") is not None
FULL_DEPS_AVAILABLE = all(
    importlib.util.find_spec(name) is not None for name in ("git", "github", "dotenv")
)


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
