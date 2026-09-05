# -*- coding: utf-8 -*-
"""
一键托管流水线
==============

步骤：初始化 Git 仓库 → 补全 .gitignore → 敏感扫描 → AI README →
     首次提交 → 创建远程仓库 → 推送。

通过 progress_cb(percent, message) 向 UI 汇报进度（Streamlit 进度条）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional, Sequence

from config import settings
from core.ai_engine import AIEngine, AIEngineError
from core.git_engine import (
    GitEngineError,
    add_remote,
    commit,
    ensure_gitignore,
    get_current_branch,
    get_diff,
    get_repo,
    get_status_summary,
    get_tree_summary,
    has_commits,
    init_repo,
    push,
    stage_all,
)
from core.github_client import GitHubClient, GitHubClientError
from core.security_guard import SecurityGuard
from models import HostingResult

ProgressCb = Callable[[int, str], None]


class HostingService:
    """一键托管业务流水线。"""

    def __init__(self, github: Optional[GitHubClient] = None, ai: Optional[AIEngine] = None):
        self.github = github or GitHubClient()
        self.ai = ai or AIEngine()
        self.guard = SecurityGuard()

    # ------------------------------------------------------------------
    def run(
        self,
        path: Path,
        repo_name: str,
        visibility: str = "private",
        description: str = "",
        use_ai_readme: bool = True,
        readme_languages: Sequence[str] = ("zh-CN", "en"),
        force: bool = False,
        progress_cb: Optional[ProgressCb] = None,
    ) -> HostingResult:
        """执行完整托管流程。"""
        target = Path(path).resolve()
        if not target.is_dir():
            raise GitEngineError(f"路径不是目录：{target}")

        def emit(percent: int, message: str) -> None:
            if progress_cb:
                progress_cb(percent, message)

        emit(5, "初始化 Git 仓库...")
        repo = init_repo(target, settings.default_branch)

        emit(10, "检查 .gitignore...")
        if ensure_gitignore(repo):
            emit(12, "已补全默认 .gitignore")

        emit(20, "敏感信息扫描...")
        findings = self.guard.scan_path(target)
        if findings and not force:
            first = findings[0]
            raise GitEngineError(
                f"敏感信息拦截：{first['file']}:{first['line']} [{first['pattern']}]。"
                "请移除硬编码密钥后重试（--force 可跳过，不推荐）。"
            )

        readme_generated = False
        readme_files: list = []
        if use_ai_readme and (not (target / "README.md").exists() or force):
            emit(35, f"AI 生成 README（{', '.join(readme_languages)}）...")
            contents = self.ai.generate_readme_i18n(
                repo_name,
                tree_summary=get_tree_summary(repo),
                language_hints=_guess_language(target),
                languages=readme_languages,
            )
            for filename, content in contents.items():
                (target / filename).write_text(content, encoding="utf-8")
                readme_files.append(filename)
            readme_generated = True

        emit(55, "创建初始提交...")
        if not has_commits(repo):
            stage_all(repo)
            diff = get_diff(repo)
            try:
                message = self.ai.generate_commit_message(
                    diff.diff_text, diff.diff_stat, hint="初始化项目"
                )
            except AIEngineError:
                message = "chore: 初始化项目"
            short = commit(repo, message)
        else:
            status = get_status_summary(repo)
            if status["staged"] or status["unstaged"] or status["untracked"]:
                stage_all(repo)
                short = commit(repo, "chore: 初始化项目文件")
            else:
                short = get_repo(target).head.commit.hexsha[:8]

        emit(70, "创建远程仓库...")
        try:
            remote_repo = self.github.create_repository(
                repo_name, description=description or f"{repo_name} —— 由 GitHub-AI-Studio 托管",
                private=(visibility == "private"),
            )
        except GitHubClientError as exc:
            raise GitEngineError(f"创建远程仓库失败：{exc}") from exc

        emit(85, "关联远程并推送...")
        add_remote(repo, "origin", remote_repo.clone_url)
        branch = get_current_branch(repo)
        push(repo, "origin", branch)
        emit(100, "完成")

        return HostingResult(
            repo_url=remote_repo.html_url,
            branch=branch,
            commit_sha=short,
            readme_generated=readme_generated,
            readme_files=readme_files,
        )


def _guess_language(path: Path) -> str:
    """根据目录内文件推断技术栈（README 提示用）。"""
    hints = []
    for pattern, label in [
        ("pyproject.toml", "Python"), ("requirements.txt", "Python"),
        ("package.json", "JavaScript/TypeScript"), ("Cargo.toml", "Rust"),
        ("go.mod", "Go"), ("pom.xml", "Java"), ("Dockerfile", "Docker"),
    ]:
        if (path / pattern).exists():
            hints.append(label)
    return ", ".join(hints) or "Python 3.10+"
