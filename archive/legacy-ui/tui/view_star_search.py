# -*- coding: utf-8 -*-
"""视图 5：🔍 Star 仓库自然语言语义搜索。"""

from __future__ import annotations

from rich.panel import Panel
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Input, Label, Static

from services.star_search_service import StarSearchService


class StarSearchView(Vertical):
    """语义搜索视图：输入自然语言需求 → 从 Star 仓库中匹配 Top N。"""

    def compose(self) -> ComposeResult:
        yield Label("🔍 Star 仓库语义搜索（例：好用的 Python 截图库）")
        yield Horizontal(
            Input(placeholder="输入你的需求...", id="star_query"),
            Button("🔍 搜索", id="star_search", variant="primary"),
        )
        yield VerticalScroll(id="star_results")
        yield Static("", id="star_status")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "star_search":
            self.run_worker(self._search(), thread=True)

    async def _search(self) -> None:
        def set_status(text: str) -> None:
            self.query_one("#star_status", Static).update(text)

        try:
            query = self.query_one("#star_query", Input).value.strip()
            set_status("🔍 正在检索 Star 仓库并语义匹配...")
            results = StarSearchService().search(query)
            self.call_from_thread(self._render, results)
        except Exception as exc:  # noqa: BLE001
            set_status(f"❌ {exc}")

    def _render(self, results: list) -> None:
        box = self.query_one("#star_results", VerticalScroll)
        box.remove_children()
        for item in results:
            repo = item["repo"]
            text = Text()
            text.append(f"⭐ {repo.stars} Stars · {repo.language or '多语言'}\n", style="yellow")
            if repo.description:
                text.append(f"{repo.description}\n", style="white")
            text.append(f"💡 {item['reason']}", style="dim")
            box.mount(Static(
                Panel(
                    text,
                    title=f"{repo.full_name}  🔥 {item['score']:.1f}/10",
                    border_style="green",
                )
            ))
        self.query_one("#star_status", Static).update(f"✅ 找到 {len(results)} 个匹配仓库")
