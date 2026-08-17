# -*- coding: utf-8 -*-
"""
数据传输对象（DTO / Dataclass）
===============================

规范 Core / Service / UI 各层之间的数据形状，避免使用裸 dict 传递，
提升类型安全与可维护性。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class TrendingRepo:
    """GitHub 热榜项目（含 AI 中文定位与摘要）。"""

    name: str                       # owner/repo
    url: str
    description: str = ""           # 原始英文描述
    language: str = ""
    stars_total: int = 0            # 总 Star 数
    stars_today: int = 0            # 今日新增
    match_score: float = 0.0        # AI 匹配度评分（0-10）
    tags: List[str] = field(default_factory=list)  # 技术标签（保留英文原文）
    zh_position: str = ""           # AI 生成的中文技术定位（保留专业英文名词）
    zh_summary: str = ""            # AI 生成的中文亮点摘要
    learning_points: str = ""       # AI 提炼的核心学习点（中文，供看板卡片展示）
    match_reason: str = ""          # 与用户兴趣的匹配原因
    overview: str = ""              # 深度研读：2~3 句项目背景与创立初衷
    pain_points: str = ""           # 深度研读：项目解决的痛点
    features: List[str] = field(default_factory=list)   # 深度研读：3~4 条核心功能（带细节）
    use_cases: str = ""             # 深度研读：适用场景与目标人群
    tech_highlights: str = ""       # 深度研读：架构与技术优势
    compact_position: str = ""      # 极简总结：一句话定位（≤35 字）
    compact_pain: str = ""          # 极简总结：核心痛点（≤35 字）
    compact_highlights: List[str] = field(default_factory=list)  # 极简总结：核心亮点（每条 ≤35 字）

    def to_dict(self) -> dict:
        """转为 dict（AI 请求 / Notion 归档时使用）。"""
        return {
            "name": self.name,
            "url": self.url,
            "description": self.description,
            "language": self.language,
            "stars_total": self.stars_total,
            "stars_today": self.stars_today,
            "match_score": self.match_score,
            "tags": list(self.tags),
            "zh_position": self.zh_position,
            "zh_summary": self.zh_summary,
            "learning_points": self.learning_points,
            "match_reason": self.match_reason,
            "overview": self.overview,
            "pain_points": self.pain_points,
            "features": list(self.features),
            "use_cases": self.use_cases,
            "tech_highlights": self.tech_highlights,
            "compact_position": self.compact_position,
            "compact_pain": self.compact_pain,
            "compact_highlights": list(self.compact_highlights),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TrendingRepo":
        """从 dict 还原对象。"""
        return cls(
            name=data.get("name", ""),
            url=data.get("url", ""),
            description=data.get("description", ""),
            language=data.get("language", ""),
            stars_total=data.get("stars_total", 0) or 0,
            stars_today=data.get("stars_today", 0) or 0,
            match_score=data.get("match_score", 0.0) or 0.0,
            tags=list(data.get("tags") or []),
            zh_position=data.get("zh_position", ""),
            zh_summary=data.get("zh_summary", ""),
            learning_points=data.get("learning_points", ""),
            match_reason=data.get("match_reason", ""),
            overview=data.get("overview", ""),
            pain_points=data.get("pain_points", ""),
            features=list(data.get("features") or []),
            use_cases=data.get("use_cases", ""),
            tech_highlights=data.get("tech_highlights", ""),
            compact_position=data.get("compact_position", ""),
            compact_pain=data.get("compact_pain", ""),
            compact_highlights=list(data.get("compact_highlights") or []),
        )


@dataclass
class CommitProposal:
    """AI 生成的提交提案（供 UI 确认后执行）。"""

    message: str
    diff_stat: str = ""
    file_count: int = 0
    sensitive_hits: List[dict] = field(default_factory=list)


@dataclass
class RepoInfo:
    """Star 仓库信息（供语义搜索）。"""

    full_name: str
    html_url: str
    description: str = ""
    language: str = ""
    stars: int = 0
    forks: int = 0

    def to_dict(self) -> dict:
        return {
            "full_name": self.full_name,
            "html_url": self.html_url,
            "description": self.description,
            "language": self.language,
            "stars": self.stars,
            "forks": self.forks,
        }


@dataclass
class HostingResult:
    """一键托管流水线的执行结果。"""

    repo_url: str
    branch: str
    commit_sha: str
    readme_generated: bool
    readme_files: List[str] = field(default_factory=list)


@dataclass
class ReleaseInfo:
    """发版信息（Tag + 生成的 CHANGELOG）。"""

    tag: str
    changelog: str
    title: str = ""
    previous_tag: Optional[str] = None
    commits_count: int = 0


@dataclass
class PipelineResult:
    """热榜流水线（抓取 → AI 翻译 → 推送 → Notion 归档）的执行结果。"""

    success: bool
    items: List[TrendingRepo] = field(default_factory=list)
    pushed_channels: Dict[str, bool] = field(default_factory=dict)
    notion_page_url: Optional[str] = None
    error: str = ""


@dataclass
class WorkLog:
    """Git 工作日报 / 周报。"""

    period: str                  # today / week
    markdown: str
    commits_count: int = 0
