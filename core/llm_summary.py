# -*- coding: utf-8 -*-
"""
热榜 LLM 摘要与推送卡片格式化（核心：防止过度中文翻译）
========================================================

规范（无论中文/英文模式均生效）：
    1. 项目名与账号名强制保留 GitHub 原始格式 `owner/repo`，严禁翻译成中文；
    2. 推送正文使用统一标准化卡片排版：
           🔥 {owner}/{repo_name} ({stars} Stars)
           🎯 核心定位：{1 句话中文/双语提炼项目作用}
           💡 关键亮点：{1~2 条技术优势或适用场景}
           ⭐ 语言与标签：{Primary Language} · {Tags}
    3. 链接与按钮保留标准 Icon/英文（🔗 Open in GitHub）。
"""

from __future__ import annotations

import re
from typing import List, Optional, Sequence

from models import TrendingRepo

# 深度研读板块的单条字数上限（25~30 字区间，统一按 30 截断保护）
SECTION_MAX_CHARS = 30


# ---------------------------------------------------------------------------
# 极致精炼总结 System Prompt（供 AIEngine.generate_compact_summary 使用）
# ---------------------------------------------------------------------------
COMPACT_SUMMARY_SYSTEM_PROMPT = (
    "你是一个技术快报助手。请用极简中文对 GitHub 项目进行总结，"
    "输出格式必须严格为以下两行，且总字数不得超过 35 字，绝不多写一个字：\n"
    "📌 定位：[15字以内说明项目干什么]\n"
    "💡 亮点：[20字以内说明核心优势]\n"
    "【硬性约束】项目名与 GitHub 账号名必须保留英文原格式 owner/repo，严禁翻译或改写；"
    "禁止堆砌语言列表（如 Python, TypeScript, Rust...），统一压缩为“支持 10+ 主流语言”。\n"
    '必须返回 JSON：{"position": "≤15字", "highlights": ["≤20字"]}，'
    "highlights 最多 1 条。只返回 JSON，不要输出任何其他文字。"
)


def _truncate_text(text: str, limit: int) -> str:
    """按字符截断，优先在标点处断句。"""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for sep in ("。", "；", "，", ". ", "; ", ", "):
        idx = cut.rfind(sep)
        if idx > 0:
            return cut[: idx + len(sep)].strip()
    return cut.strip()


def apply_compact_rules(data: dict) -> dict:
    """把紧凑总结压缩到硬性规则：定位 ≤15 字、亮点 ≤20 字、总量 ≤35 字。"""
    position = _truncate_text(data.get("position"), 15)
    highlights = [
        _truncate_text(h, 20)
        for h in (data.get("highlights") or [])
        if h and str(h).strip()
    ][:1]

    # 语言列表压缩（保险兜底）
    if position.count("，") + position.count(",") >= 3:
        position = "支持 10+ 主流语言"
    highlights = [
        "支持 10+ 主流语言" if h.count("，") + h.count(",") >= 3 else h
        for h in highlights
    ]

    total = len(position) + sum(len(h) for h in highlights)
    if total > 35:
        overflow = total - 35
        position = _truncate_text(position, max(0, len(position) - overflow))
    return {"position": position, "highlights": highlights}


def apply_section_rules(data: dict) -> dict:
    """把深度研读五板块压缩到 25~30 字：每个字段 ≤30 字、features 每条 ≤30 字。"""
    overview = _truncate_text(data.get("overview"), SECTION_MAX_CHARS)
    pain_points = _truncate_text(data.get("pain_points"), SECTION_MAX_CHARS)
    use_cases = _truncate_text(data.get("use_cases"), SECTION_MAX_CHARS)
    tech_highlights = _truncate_text(data.get("tech_highlights"), SECTION_MAX_CHARS)
    features = [
        _truncate_text(f, SECTION_MAX_CHARS)
        for f in (data.get("features") or [])
        if f and str(f).strip()
    ][:3]
    return {
        "overview": overview,
        "pain_points": pain_points,
        "features": features,
        "use_cases": use_cases,
        "tech_highlights": tech_highlights,
    }


def format_compact_summary(data: dict) -> str:
    """渲染两行极简模板（总字数 ≤35）：📌 定位 + 💡 亮点。"""
    position = str(data.get("position") or "").strip()
    highlights = [str(h).strip() for h in (data.get("highlights") or []) if str(h).strip()][:1]
    lines = []
    if position:
        lines.append(f"📌 **定位**：{position}")
    if highlights:
        lines.append(f"💡 **亮点**：{highlights[0]}")
    return "\n".join(lines)


def format_stars(num: int) -> str:
    """把 Star 数格式化为 56.2k / 1.3M 形式。"""
    num = num or 0
    if num >= 1_000_000:
        return f"{num / 1_000_000:.1f}M"
    if num >= 1_000:
        return f"{num / 1_000:.1f}k"
    return str(num)


def split_highlights(repo: TrendingRepo) -> List[str]:
    """从 AI 学习点/摘要中提取 1~2 条技术亮点。"""
    raw = (repo.learning_points or repo.zh_summary or repo.description or "").strip()
    if not raw:
        return ["多技术栈实践 / 工程化参考"]
    parts = [p.strip() for p in re.split(r"[/；;，,]", raw) if p.strip()]
    # 单条过长时截断为两句
    if len(parts) >= 2:
        return parts[:2]
    text = parts[0]
    if len(text) > 60:
        return [text[:60], text[60:120].strip("。；;，,") or text[:60]]
    return [text]


def split_features(repo: TrendingRepo) -> List[str]:
    """优先返回深度研读 features，缺失时回退学习点/摘要。"""
    features = [f.strip() for f in (repo.features or []) if f.strip()]
    return features[:4] or split_highlights(repo)


def build_repo_card(repo: TrendingRepo) -> str:
    """构造单条标准化推送卡片（项目名原样保留，绝不翻译）。"""
    name = (repo.name or "").strip()  # owner/repo，保持 GitHub 原始格式
    if "/" not in name:
        name = f"{name}/unknown"
    header = f"🔥 {name} ({format_stars(repo.stars_total)} Stars)"
    position = (
        repo.compact_position or repo.overview or repo.zh_position
        or repo.description or "Open-source project"
    ).strip()
    highlights = "；".join(
        repo.compact_highlights
        or split_features(repo)
    )
    lang = repo.language or "Multi-language"
    tags = " · ".join([lang] + [str(t) for t in (repo.tags or []) if str(t).strip()][:3])
    return "\n".join([
        header,
        f"🎯 核心定位：{position[:120]}",
        f"💡 关键亮点：{highlights[:160]}",
        f"⭐ 语言与标签：{tags[:120]}",
    ])


def build_trending_digest(
    repos: Sequence[TrendingRepo], skills_radar: Optional[Sequence[str]] = None
) -> str:
    """组装每日趋势日报：技能雷达 + 标准化卡片（含 GitHub 原文链接）。"""
    repos = list(repos)
    radar = "、".join(str(t) for t in (skills_radar or []) if str(t).strip())
    lines: List[str] = []
    if radar:
        lines.append(f"**📡 今日技能雷达**：{radar}")
    lines.append("")
    for i, repo in enumerate(repos, start=1):
        lines.append(f"{i}. {build_repo_card(repo)}")
        lines.append(f"🔗 Open in GitHub：{repo.url}")
        lines.append("")
    return "\n".join(lines).strip()
