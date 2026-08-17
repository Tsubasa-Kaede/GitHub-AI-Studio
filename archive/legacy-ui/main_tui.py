# -*- coding: utf-8 -*-
"""
GitHub-AI-Studio 纯终端 TUI 主入口
===================================

运行：
    python main_tui.py

快捷键：
    F5     刷新热榜
    Ctrl+S 保存配置
    Ctrl+Q 退出
"""

from __future__ import annotations

from tui.app import GitHubAIStudioApp


def main() -> None:
    """启动 Textual 终端控制台。"""
    GitHubAIStudioApp().run()


if __name__ == "__main__":
    main()
