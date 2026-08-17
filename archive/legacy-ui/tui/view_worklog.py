# -*- coding: utf-8 -*-
"""视图 6：📋 开发者 Git 工作日报 / 周报生成器。"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Label, Select, Static, TextArea

from services.worklog_service import WorklogService


class WorklogView(Vertical):
    """工作日报视图：读取今天/本周提交 → AI 汇总 Markdown → 一键复制。"""

    def compose(self) -> ComposeResult:
        yield Label("📋 Git 工作日报 / 周报生成器")
        yield Input(placeholder="本地 Git 仓库路径", id="worklog_path")
        yield Horizontal(
            Select(
                [("📅 今日日报", "today"), ("📆 本周周报", "week")],
                value="today", id="worklog_period",
            ),
            Button("✨ 生成日报", id="worklog_generate", variant="primary"),
            Button("📋 复制到剪贴板", id="worklog_copy"),
        )
        yield TextArea("", id="worklog_text", read_only=True)
        yield Static("", id="worklog_status")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "worklog_generate":
            self.run_worker(self._generate(), thread=True)
        elif event.button.id == "worklog_copy":
            text = self.query_one("#worklog_text", TextArea).text
            if text:
                self.app.copy_to_clipboard(text)
                self.notify("已复制到剪贴板")

    async def _generate(self) -> None:
        try:
            path = self.query_one("#worklog_path", Input).value.strip()
            period = str(self.query_one("#worklog_period", Select).value)
            result = WorklogService().generate(path, period)
            self.query_one("#worklog_text", TextArea).text = result.markdown
            self.query_one("#worklog_status", Static).update(
                f"✅ 已基于 {result.commits_count} 条提交生成 {result.period} 日报"
            )
        except Exception as exc:  # noqa: BLE001
            self.query_one("#worklog_status", Static).update(f"❌ {exc}")
