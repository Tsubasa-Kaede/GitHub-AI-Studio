# -*- coding: utf-8 -*-
"""
services 业务流水线层：组合 core 原子能力，供 UI 与 CLI 调用。

包含：
    hosting_service.py    —— 一键托管流水线
    trending_service.py   —— 热榜抓取 → AI 翻译 → 推送 → Notion 归档
    release_service.py    —— 提取提交 → AI 格式化 → 发布 Release
"""
