# -*- coding: utf-8 -*-
"""视图 1：🚀 一键托管 & 多语言 README 控制台。"""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Button, Input, Label, Select, Static

from services.hosting_service import HostingService


class HostingView(Vertical):
    """一键托管视图：本地目录 → AI 多语言 README → 建仓 → 推送。"""

    def compose(self) -> ComposeResult:
        yield Label("🚀 一键项目托管（AI 自动生成多语言 README 并推送 GitHub）")
        yield Input(placeholder="本地项目路径，如 C:\\Users\\you\\my-project", id="host_path")
        yield Input(placeholder="远程仓库名（留空自动取目录名）", id="host_repo_name")
        yield Select(
            [("私有 private", "private"), ("公开 public", "public")],
            value="private", id="host_visibility", prompt="仓库可见性",
        )
        yield Input(
            placeholder="多语言 README（逗号分隔）",
            value="zh-CN,en", id="host_langs",
        )
        yield Button("🚀 一键托管", id="host_run", variant="primary")
        yield Static("", id="host_output")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """点击托管按钮 → 后台线程执行流水线。"""
        if event.button.id == "host_run":
            self.run_worker(self._run(), thread=True)

    async def _run(self) -> None:
        """执行托管流水线并把进度输出到界面。"""

        def set_output(text: str) -> None:
            self.query_one("#host_output", Static).update(text)

        def on_progress(percent: int, message: str) -> None:
            # 线程安全地更新 UI
            self.call_from_thread(set_output, f"[{percent:>3}%] {message}")

        try:
            path = self.query_one("#host_path", Input).value.strip()
            if not path:
                set_output("❌ 请先填写本地项目路径")
                return
            repo_name = self.query_one("#host_repo_name", Input).value.strip() or Path(path).name
            visibility = str(self.query_one("#host_visibility", Select).value)
            langs = [
                x.strip() for x in self.query_one("#host_langs", Input).value.split(",") if x.strip()
            ] or ["zh-CN", "en"]
            result = HostingService().run(
                path=path, repo_name=repo_name, visibility=visibility,
                readme_languages=langs, progress_cb=on_progress,
            )
            files = ", ".join(result.readme_files) if result.readme_files else "保留原文件"
            set_output(f"🎉 托管成功：{result.repo_url}\n提交 {result.commit_sha} · README：{files}")
            self.notify("一键托管成功", severity="success")
        except Exception as exc:  # noqa: BLE001
            set_output(f"❌ 托管失败：{exc}")
            self.notify("托管失败", severity="error")
