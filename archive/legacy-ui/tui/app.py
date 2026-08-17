# -*- coding: utf-8 -*-
"""
Textual TUI 主应用
===================

职责：渲染 Header / Footer / TabbedContent 六大功能视图 + 设置页，
     并声明全局快捷键：
         F5        —— 刷新热榜
         Ctrl+S    —— 保存配置
         Ctrl+Q    —— 退出
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, TabbedContent, TabPane

from tui.view_commit import CommitView
from tui.view_hosting import HostingView
from tui.view_release import ReleaseView
from tui.view_settings import SettingsView
from tui.view_star_search import StarSearchView
from tui.view_trending import TrendingView
from tui.view_worklog import WorklogView


class GitHubAIStudioApp(App):
    """纯终端 GitHub 智能化管理控制台主应用。"""

    TITLE = "GitHub-AI-Studio"
    SUB_TITLE = "纯终端 GitHub 智能化管理控制台"

    BINDINGS = [
        Binding("f5", "refresh_trending", "刷新热榜"),
        Binding("ctrl+s", "save_settings", "保存配置"),
        Binding("ctrl+q", "quit", "退出"),
    ]

    CSS = """
    TabPane { padding: 1 2; }
    #trending_cards { height: 1fr; }
    Button { margin: 0 1 0 0; }
    Input, Select, TextArea { margin: 0 0 1 0; }
    """

    def compose(self) -> ComposeResult:
        """组装主界面：顶部状态栏 + 六个功能 Tab + 设置页 + 底部快捷键栏。"""
        yield Header(show_clock=True)
        with TabbedContent(id="main-tabs"):
            with TabPane("🚀 一键托管", id="tab-hosting"):
                yield HostingView()
            with TabPane("📝 AI Commit", id="tab-commit"):
                yield CommitView()
            with TabPane("🔥 中文热榜", id="tab-trending"):
                yield TrendingView()
            with TabPane("📦 自动发版", id="tab-release"):
                yield ReleaseView()
            with TabPane("🔍 Star 搜索", id="tab-star"):
                yield StarSearchView()
            with TabPane("📋 工作日报", id="tab-worklog"):
                yield WorklogView()
            with TabPane("⚙️ 设置", id="tab-settings"):
                yield SettingsView()
        yield Footer()

    # ------------------------------------------------------------------
    # 全局快捷键动作
    # ------------------------------------------------------------------
    def action_refresh_trending(self) -> None:
        """F5：刷新热榜（委托热榜视图）。"""
        self.query_one(TrendingView).start_fetch()

    def action_save_settings(self) -> None:
        """Ctrl+S：保存配置（委托设置视图）。"""
        self.query_one(SettingsView).save()
