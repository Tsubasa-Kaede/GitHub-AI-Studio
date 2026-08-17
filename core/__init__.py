# -*- coding: utf-8 -*-
"""
core 原子引擎层：不依赖 UI / Service 的任何逻辑。

包含：
    git_engine.py     —— Git 基础操作（GitPython）
    github_client.py  —— GitHub API 操作（PyGithub）
    ai_engine.py      —— OpenAI 结构化输出引擎
    push_engine.py    —— 多端推送（Ntfy / 飞书 / 钉钉 / 企微 / 邮件）
    notion_engine.py  —— Notion 数据库归档
"""

__version__ = "1.0.0"
