# -*- coding: utf-8 -*-
"""视图 3：🔥 兴趣中文热榜（Rich.Panel 卡片瀑布流）。"""

from __future__ import annotations

from typing import List

from rich.console import Group
from rich.panel import Panel
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Static

from core.notion_engine import NotionArchiver
from core.ntfy_engine import NtfyEngine
from models import TrendingRepo
from services.trending_service import run_daily_trending_pipeline


def _fmt(num: int) -> str:
    """大数字格式化：56200 → 56.2k。"""
    num = num or 0
    if num >= 1_000_000:
        return f"{num / 1_000_000:.1f}M"
    if num >= 1_000:
        return f"{num / 1_000:.1f}k"
    return str(num)


class TrendingView(Vertical):
    """热榜视图：抓取 → AI 评分翻译 → 卡片展示 → Ntfy 推送 / Notion 归档。"""

    def __init__(self) -> None:
        super().__init__()
        self._items: List[TrendingRepo] = []

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Button("🌐 抓取并 AI 翻译", id="trend_fetch", variant="primary"),
            Button("📱 推送到 Ntfy", id="trend_push"),
            Button("📚 归档 Notion", id="trend_archive"),
        )
        yield VerticalScroll(Vertical(Static("", id="trending_cards")))
        yield Static("按 F5 或点击「抓取并 AI 翻译」获取今日热榜", id="trend_status")

    # ------------------------------------------------------------------
    def start_fetch(self) -> None:
        """F5 快捷键入口。"""
        self.run_worker(self._fetch(), thread=True)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """分发全局与卡片级按钮。"""
        button_id = event.button.id or ""
        if button_id == "trend_fetch":
            self.start_fetch()
        elif button_id == "trend_push":
            self.run_worker(self._push_all(), thread=True)
        elif button_id == "trend_archive":
            self.run_worker(self._archive_all(), thread=True)

    # ------------------------------------------------------------------
    async def _fetch(self) -> None:
        def set_status(text: str) -> None:
            self.query_one("#trend_status", Static).update(text)

        def on_progress(percent: int, message: str) -> None:
            self.call_from_thread(set_status, f"[{percent:>3}%] {message}")

        try:
            result = run_daily_trending_pipeline(
                do_push=False, do_archive=False, progress_cb=on_progress
            )
            if not result.success:
                self.call_from_thread(set_status, f"❌ {result.error}")
                return
            self._items = result.items
            self.call_from_thread(self._render_cards)
        except Exception as exc:  # noqa: BLE001
            self.call_from_thread(set_status, f"❌ {exc}")

    def _render_cards(self) -> None:
        """把热榜渲染为 Rich.Panel 卡片瀑布流（Group 单容器，避免异步增删问题）。"""
        panels = []
        for i, repo in enumerate(self._items, start=1):
            title = f"{i}. {repo.name}  🔥 匹配度 {repo.match_score:.1f}/10"
            panels.append(Panel(_card_text(repo), title=title, border_style="blue", padding=(0, 1)))
        self.query_one("#trending_cards", Static).update(Group(*panels) if panels else "（暂无数据）")
        self.query_one("#trend_status", Static).update(f"✅ 共 {len(self._items)} 条推荐（F5 刷新）")

    async def _push_all(self) -> None:
        try:
            result = NtfyEngine().send_trending(self._items)
            self.query_one("#trend_status", Static).update(f"📱 全部推送结果：{result}")
            self.notify(f"已推送 {result.get('sent', 0)}/{len(self._items)} 条")
        except Exception as exc:  # noqa: BLE001
            self.query_one("#trend_status", Static).update(f"❌ {exc}")

    async def _archive_all(self) -> None:
        try:
            urls = NotionArchiver().archive_many(self._items)
            self.query_one("#trend_status", Static).update(f"📚 已归档 {len(urls)} 条")
        except Exception as exc:  # noqa: BLE001
            self.query_one("#trend_status", Static).update(f"❌ {exc}")


def _card_text(repo: TrendingRepo) -> Text:
    """构造单张卡片的 Rich 文本内容。"""
    text = Text()
    if repo.zh_position:
        text.append(f"🎯 {repo.zh_position}\n", style="bold cyan")
    text.append(f"💡 {repo.zh_summary or repo.description}\n", style="white")
    text.append(
        f"⭐ {_fmt(repo.stars_total)} Stars · 今日 +{_fmt(repo.stars_today)} · {repo.language or '多语言'}\n",
        style="yellow",
    )
    tags = " ".join(f"#{tag}" for tag in repo.tags) or "#多语言"
    text.append(f"🏷️ 技术标签：{tags}\n", style="magenta")
    if repo.match_reason:
        text.append(f"💡 {repo.match_reason}", style="dim")
    return text
