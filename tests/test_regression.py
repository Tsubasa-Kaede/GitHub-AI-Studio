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


GITPYTHON_AVAILABLE = importlib.util.find_spec("git") is not None


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
