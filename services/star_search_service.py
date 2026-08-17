# -*- coding: utf-8 -*-
"""
Star 仓库语义搜索流水线
========================

获取当前账号 Star 仓库 → AI 自然语言语义匹配 → 返回 Top N（含评分与理由）。
"""

from __future__ import annotations

from typing import List, Optional

from core.ai_engine import AIEngine
from core.github_client import GitHubClient
from models import RepoInfo


class StarSearchError(RuntimeError):
    """Star 搜索失败。"""


class StarSearchService:
    """Star 仓库语义搜索服务。"""

    def __init__(self, github: Optional[GitHubClient] = None, ai: Optional[AIEngine] = None):
        self.github = github or GitHubClient()
        self.ai = ai or AIEngine()

    def search(self, query: str, limit: int = 300, top_n: int = 5) -> List[dict]:
        """按自然语言查询 Star 仓库，返回 [{repo, score, reason}]。"""
        query = (query or "").strip()
        if not query:
            raise StarSearchError("请输入搜索需求，例如：好用的 Python 截图库")
        repos: List[RepoInfo] = self.github.get_starred_repos(limit)
        if not repos:
            raise StarSearchError("当前账号还没有 Star 任何仓库。")
        results = self.ai.semantic_search_starred(repos, query, top_n)
        if not results:
            raise StarSearchError("未找到匹配的仓库，请换一种问法。")
        return results
