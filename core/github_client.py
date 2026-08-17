# -*- coding: utf-8 -*-
"""
GitHub 原子引擎（PyGithub 封装）
================================

只负责与 GitHub API 交互：认证、创建仓库、发布 Release、PR 评论。
凭证来源由 config.resolve_github_token() 统一决定（.env 或 gh CLI）。
所有异常统一翻译为 GitHubClientError。
"""

from __future__ import annotations

from typing import Dict, List, Optional

import requests
from github import (
    BadCredentialsException,
    Github,
    GithubException,
    RateLimitExceededException,
    TwoFactorException,
    UnknownObjectException,
)
from github.Repository import Repository

from config import resolve_github_token
from models import RepoInfo

# 评论中标记 AI 审查报告的锚点（用于去重 / 更新旧报告）
AI_REVIEW_MARKER = "<!-- GitHub-AI-Studio: ai-review -->"


class GitHubClientError(RuntimeError):
    """GitHub API 操作失败。"""


def _translate(action: str, exc: GithubException) -> GitHubClientError:
    """PyGithub 异常 → 中文友好错误。"""
    if isinstance(exc, RateLimitExceededException):
        return GitHubClientError(f"{action} 失败：GitHub API 速率限制，请稍后重试。")
    if exc.status == 401:
        return GitHubClientError(f"{action} 失败：Token 无效或已过期（401）。")
    if exc.status == 403:
        return GitHubClientError(f"{action} 失败：权限不足（403），请检查 Token 权限。")
    if exc.status == 404:
        return GitHubClientError(f"{action} 失败：资源不存在（404）。")
    data = exc.data if isinstance(exc.data, dict) else {}
    return GitHubClientError(f"{action} 失败：{data.get('message') or exc}")


class GitHubClient:
    """GitHub API 客户端（认证 / 仓库 / Release / PR 评论）。"""

    def __init__(self, token: Optional[str] = None, timeout: Optional[int] = None, retry: int = 3):
        from config import settings

        self.token, self.source = (token, "manual") if token else resolve_github_token()
        self.timeout = timeout or settings.request_timeout
        self._gh = Github(self.token, timeout=self.timeout, retry=retry, per_page=100)
        self._user = None

    # ------------------------------------------------------------------
    # 认证
    # ------------------------------------------------------------------
    def authenticate(self) -> str:
        """校验 Token 并返回登录用户名。"""
        try:
            self._user = self._gh.get_user()
            return self._user.login
        except BadCredentialsException as exc:
            raise GitHubClientError("GitHub Token 无效或已过期，请检查 .env 或重新 gh auth login。") from exc
        except TwoFactorException as exc:
            raise GitHubClientError("账号开启了两步验证，请使用 Personal Access Token。") from exc
        except GithubException as exc:
            raise _translate("GitHub 登录验证", exc) from exc
        except requests.exceptions.Timeout as exc:
            raise GitHubClientError(f"GitHub 请求超时（{self.timeout}s），请检查网络/代理。") from exc
        except requests.exceptions.ConnectionError as exc:
            raise GitHubClientError("无法连接 GitHub API：请检查网络/代理设置。") from exc

    @property
    def user(self):
        """当前认证用户（惰性认证）。"""
        if self._user is None:
            self.authenticate()
        return self._user

    def get_repository(self, full_name: str) -> Repository:
        """获取仓库对象。"""
        try:
            return self._gh.get_repo(full_name)
        except UnknownObjectException as exc:
            raise GitHubClientError(f"仓库不存在或无权访问：{full_name}") from exc
        except GithubException as exc:
            raise _translate(f"获取仓库 {full_name}", exc) from exc

    # ------------------------------------------------------------------
    # 仓库
    # ------------------------------------------------------------------
    def create_repository(
        self,
        name: str,
        description: str = "",
        private: bool = True,
        auto_init: bool = False,
        gitignore_template: Optional[str] = None,
    ) -> Repository:
        """创建远程仓库；同名已存在时给出中文提示。"""
        try:
            return self.user.create_repo(
                name=name,
                description=description or "Created by GitHub-AI-Studio",
                private=bool(private),
                auto_init=bool(auto_init),
                gitignore_template=gitignore_template,
            )
        except GithubException as exc:
            if exc.status == 422:
                raise GitHubClientError(
                    f"远程仓库 {name!r} 已存在（或名称不合法），请更换仓库名。"
                ) from exc
            raise _translate(f"创建仓库 {name}", exc) from exc

    # ------------------------------------------------------------------
    # Release
    # ------------------------------------------------------------------
    def create_release(
        self,
        full_name: str,
        tag_name: str,
        name: str = "",
        body: str = "",
        target_commitish: Optional[str] = None,
        draft: bool = False,
        prerelease: bool = False,
    ) -> dict:
        """创建 GitHub Release（Tag 不存在时自动创建）。"""
        repo = self.get_repository(full_name)
        try:
            release = repo.create_git_release(
                tag=tag_name,
                name=name or tag_name,
                message=body or "",
                target_commitish=target_commitish or repo.default_branch,
                draft=draft,
                prerelease=prerelease,
            )
            return {"tag": release.tag_name, "name": release.title, "url": release.html_url}
        except GithubException as exc:
            if exc.status == 422:
                raise GitHubClientError(f"Release 创建失败：标签 {tag_name!r} 可能已存在。") from exc
            raise _translate("创建 Release", exc) from exc

    def list_releases(self, full_name: str, limit: int = 10) -> List[dict]:
        """列出 Release（倒序）。"""
        try:
            releases = list(self.get_repository(full_name).get_releases())[:limit]
        except GithubException as exc:
            raise _translate("获取 Release 列表", exc) from exc
        return [
            {"tag": r.tag_name, "name": r.title, "published_at": str(r.published_at or ""), "url": r.html_url}
            for r in releases
        ]

    # ------------------------------------------------------------------
    # PR 审查评论（供 GitHub Actions 工作流调用）
    # ------------------------------------------------------------------
    def post_or_update_review_comment(self, full_name: str, issue_number: int, body: str) -> dict:
        """发布 AI 审查报告；存在旧报告时先删除再发布，避免刷屏。"""
        repo = self.get_repository(full_name)
        try:
            issue = repo.get_issue(issue_number)
            for comment in issue.get_comments():
                if AI_REVIEW_MARKER in (comment.body or ""):
                    comment.delete()
            created = issue.create_comment(body)
            return {"comment_id": created.id, "url": created.html_url}
        except GithubException as exc:
            raise _translate("发布 PR 评论", exc) from exc

    def get_compare_patch(self, full_name: str, base_sha: str, head_sha: str) -> str:
        """获取两个提交之间的 Patch 文本（PR 审查备用）。"""
        try:
            comparison = self.get_repository(full_name).compare(base_sha, head_sha)
        except GithubException as exc:
            raise _translate("获取 PR Diff", exc) from exc
        parts = []
        for f in comparison.files:
            parts.append(f"### {f.filename}  (+{f.additions} -{f.deletions})\n{f.patch or '(patch 过大)'}")
        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # 其他
    # ------------------------------------------------------------------
    def rate_limit(self) -> dict:
        """GitHub API 配额信息（只读，失败不阻断）。"""
        try:
            core = self._gh.get_rate_limit().core
            return {"remaining": core.remaining, "limit": core.limit, "reset_at": str(core.reset)}
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Star 仓库（语义搜索数据源）
    # ------------------------------------------------------------------
    def get_starred_repos(self, limit: int = 300) -> List[RepoInfo]:
        """获取当前账号 Star 过的仓库列表（按 Star 时间倒序）。"""
        try:
            starred = list(self.user.get_starred())[:limit]
        except GithubException as exc:
            raise _translate("获取 Star 仓库列表", exc) from exc
        return [
            RepoInfo(
                full_name=r.full_name,
                html_url=r.html_url,
                description=r.description or "",
                language=r.language or "",
                stars=r.stargazers_count,
                forks=r.forks_count,
            )
            for r in starred
        ]
