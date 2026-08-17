# -*- coding: utf-8 -*-
"""视图 4：📦 AI CHANGELOG 发版控制台。"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Label, Static, TextArea

from models import ReleaseInfo
from services.release_service import ReleaseService


class ReleaseView(Vertical):
    """发版视图：提取提交 → AI 生成 CHANGELOG → 预览编辑 → 发布 Release。"""

    def compose(self) -> ComposeResult:
        yield Label("📦 AI 自动生成 CHANGELOG & GitHub Release")
        yield Input(placeholder="本地 Git 仓库路径", id="release_path")
        yield Horizontal(
            Input(placeholder="版本 Tag，如 v1.2.0", id="release_tag"),
            Input(placeholder="GitHub 仓库全名 owner/repo", id="release_repo"),
        )
        yield Horizontal(
            Button("✨ 生成 CHANGELOG", id="release_generate", variant="primary"),
            Button("🚀 发布 Release", id="release_publish"),
        )
        yield TextArea("", id="release_changelog")
        yield Static("", id="release_output")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "release_generate":
            self.run_worker(self._generate(), thread=True)
        elif event.button.id == "release_publish":
            self.run_worker(self._publish(), thread=True)

    async def _generate(self) -> None:
        try:
            path = self.query_one("#release_path", Input).value.strip()
            tag = self.query_one("#release_tag", Input).value.strip()
            if not path or not tag:
                self.query_one("#release_output", Static).update("❌ 请填写仓库路径与 Tag")
                return
            info: ReleaseInfo = ReleaseService().generate(path, tag)
            self._info = info
            self.query_one("#release_changelog", TextArea).text = info.changelog
            self.query_one("#release_output", Static).update(
                f"✅ 基于 {info.commits_count} 条提交生成" +
                (f"，对比 {info.previous_tag}" if info.previous_tag else "")
            )
        except Exception as exc:  # noqa: BLE001
            self.query_one("#release_output", Static).update(f"❌ {exc}")

    async def _publish(self) -> None:
        try:
            info = getattr(self, "_info", None)
            full_name = self.query_one("#release_repo", Input).value.strip()
            if info is None or not full_name:
                self.query_one("#release_output", Static).update("❌ 请先生成 CHANGELOG 并填写仓库全名")
                return
            body = self.query_one("#release_changelog", TextArea).text
            result = ReleaseService().publish(full_name, info, body=body)
            self.query_one("#release_output", Static).update(f"🎉 已发布：{result['url']}")
            self.notify("Release 发布成功", severity="success")
        except Exception as exc:  # noqa: BLE001
            self.query_one("#release_output", Static).update(f"❌ {exc}")
