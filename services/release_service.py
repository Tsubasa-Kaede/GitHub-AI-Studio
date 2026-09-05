# -*- coding: utf-8 -*-
"""
AI 发版流水线
==============

Extract（提取提交历史）→ AI Format（分类生成 CHANGELOG）→ Publish（发布 Release）。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Optional

from core.ai_engine import AIEngine
from core.git_engine import get_commits_since, get_repo, list_tags
from core.github_client import GitHubClient
from models import ReleaseInfo

ProgressCb = Callable[[int, str], None]


def _version_key(tag: str) -> tuple:
    """把版本标签拆为纯数字段元组：v1.10 → (1, 10)，保证可比较。

    只取数字段（忽略 v / release 等字母前后缀），避免
    ('v', 1, 0) 与 (1, 2) 这类 int/str 混合比较的 TypeError。
    """
    return tuple(int(p) for p in re.findall(r"\d+", tag or ""))


class ReleaseService:
    """发版业务流水线。"""

    def __init__(self, github: Optional[GitHubClient] = None, ai: Optional[AIEngine] = None):
        self.github = github or GitHubClient()
        self.ai = ai or AIEngine()

    # ------------------------------------------------------------------
    def generate(self, repo_path: Path, tag: str) -> ReleaseInfo:
        """从本地仓库提取提交历史并生成 CHANGELOG 预览。"""
        repo = get_repo(Path(repo_path).resolve())
        tags = list_tags(repo)
        previous_tag = None
        if tags and tag not in tags:
            # 取最近的既有标签作为对比基线
            previous_tag = sorted(tags, key=_version_key)[-1]
        commits_text = get_commits_since(repo, previous_tag, limit=100)
        data = self.ai.format_changelog(commits_text, tag)
        changelog = self.ai.compose_changelog_markdown(data, tag)
        count = len([ln for ln in commits_text.splitlines() if ln.strip()])
        return ReleaseInfo(tag=tag, changelog=changelog, title=tag, previous_tag=previous_tag, commits_count=count)

    # ------------------------------------------------------------------
    def publish(self, full_name: str, release_info: ReleaseInfo, body: Optional[str] = None) -> dict:
        """发布 Release（body 为空时使用生成的 CHANGELOG）。"""
        return self.github.create_release(
            full_name, release_info.tag, name=release_info.title,
            body=body or release_info.changelog,
        )
