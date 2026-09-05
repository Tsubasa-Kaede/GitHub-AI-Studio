# -*- coding: utf-8 -*-
"""Tab 6：📋 开发者 Git 工作日报 / 周报生成器。"""

from __future__ import annotations

from datetime import date

import streamlit as st

from ui.components import get_worklog_service, render_error, tr
from ui import theme


def render() -> None:
    """渲染工作日报页面。"""
    theme.section_header("", tr("worklog.title"), tr("worklog.desc"))
    theme.tagline(["选择仓库", "统计周期", "AI 汇总", "下载"])

    with st.container(border=True):
        path = st.text_input(
            "本地 Git 仓库目录", placeholder="C:\\Users\\you\\my-project", key="worklog_path"
        )
        period = st.radio(
            "统计周期", ["today", "week"], horizontal=True, key="worklog_period",
            format_func=lambda x: "今日日报" if x == "today" else "本周周报",
        )
        if st.button(tr("worklog.generate"), type="primary", use_container_width=True,
                     disabled=not path, key="worklog_generate"):
            try:
                with st.spinner("AI 汇总提交记录..."):
                    result = get_worklog_service().generate(path, period)
                st.session_state["worklog_md"] = result.markdown
                st.success(f"✓ 已基于 {result.commits_count} 条提交生成")
            except Exception as exc:  # noqa: BLE001
                render_error(exc)

    markdown = st.session_state.get("worklog_md")
    if markdown:
        with st.container(border=True):
            st.code(markdown, language="markdown")
            st.download_button(
                tr("worklog.download"),
                data=markdown,
                file_name=f"worklog-{date.today().isoformat()}.md",
                mime="text/markdown",
                key="worklog_download",
            )
