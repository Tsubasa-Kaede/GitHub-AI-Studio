# -*- coding: utf-8 -*-
"""⚙️ 设置视图（Token / API Key 全部 password 遮罩）。"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Button, Input, Label, Static

import config


class SettingsView(Vertical):
    """配置视图：编辑并保存 .env（敏感字段密码遮罩）。"""

    def compose(self) -> ComposeResult:
        yield Label("⚙️ 设置（敏感字段已开启密码遮罩，Ctrl+S 快速保存）")
        # 敏感字段：全部 password=True，防止屏幕泄露
        yield Input(config.settings.github_token, password=True, placeholder="GITHUB_TOKEN（留空复用 gh CLI）", id="set_github")
        yield Input(config.settings.openai_api_key, password=True, placeholder="OPENAI_API_KEY", id="set_openai")
        yield Input(config.settings.notion_token, password=True, placeholder="NOTION_TOKEN", id="set_notion_token")
        yield Input(config.settings.ntfy_token, password=True, placeholder="NTFY_TOKEN（自建服务可选）", id="set_ntfy_token")
        # 普通字段
        yield Input(config.settings.ntfy_server, placeholder="NTFY_SERVER", id="set_ntfy_server")
        yield Input(config.settings.ntfy_topic, placeholder="NTFY_TOPIC（手机订阅主题）", id="set_ntfy_topic")
        yield Input(", ".join(config.settings.user_interests), placeholder="USER_INTERESTS", id="set_interests")
        yield Button("💾 保存配置", id="settings_save", variant="primary")
        yield Static("", id="settings_output")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "settings_save":
            self.save()

    def save(self) -> None:
        """收集所有输入并写回 .env（配置热重载，立即生效）。"""
        try:
            changed = config.update_env_file({
                "GITHUB_TOKEN": self.query_one("#set_github", Input).value,
                "OPENAI_API_KEY": self.query_one("#set_openai", Input).value,
                "NOTION_TOKEN": self.query_one("#set_notion_token", Input).value,
                "NTFY_TOKEN": self.query_one("#set_ntfy_token", Input).value,
                "NTFY_SERVER": self.query_one("#set_ntfy_server", Input).value,
                "NTFY_TOPIC": self.query_one("#set_ntfy_topic", Input).value,
                "USER_INTERESTS": self.query_one("#set_interests", Input).value,
            })
            self.query_one("#settings_output", Static).update(
                f"✅ 已保存：{', '.join(changed) if changed else '无变更'}"
            )
            self.notify("配置已保存并生效")
        except Exception as exc:  # noqa: BLE001
            self.query_one("#settings_output", Static).update(f"❌ {exc}")
