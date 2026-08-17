# -*- coding: utf-8 -*-
"""
Git 工作日报 / 周报流水线
==========================

读取指定周期（今天 / 近 7 天）的 Git 提交 → AI 汇总为结构化 Markdown。
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from core.ai_engine import AIEngine
from core.git_engine import get_commits_since_date, get_repo
from models import WorkLog


class WorklogService:
    """工作日报生成服务。"""

    def __init__(self, ai: Optional[AIEngine] = None):
        self.ai = ai or AIEngine()

    def generate(self, path: Path, period: str = "today") -> WorkLog:
        """生成日报（today）或周报（week）。"""
        period = period if period in {"today", "week"} else "today"
        repo = get_repo(Path(path).resolve())
        if period == "today":
            since_date = date.today().isoformat()
            label = "今日"
        else:
            since_date = (date.today() - timedelta(days=6)).isoformat()
            label = "本周"
        commits_text = get_commits_since_date(repo, since_date)
        markdown = self.ai.generate_worklog(commits_text, period=label)
        count = len([ln for ln in commits_text.splitlines() if ln.strip()])
        return WorkLog(period=period, markdown=markdown, commits_count=count)
