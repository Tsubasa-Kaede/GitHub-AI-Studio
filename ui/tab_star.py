# -*- coding: utf-8 -*-
"""Tab 5：🔍 Star 仓库自然语言语义搜索。"""

from __future__ import annotations

import streamlit as st

from ui.components import get_github_client, get_star_search_service, render_error, tr
from ui import theme


def render() -> None:
    """渲染 Star 语义搜索页面。"""
    theme.section_header("", tr("star.title"), tr("star.desc"))
    theme.tagline(["输入需求", "检索 Star", "AI 语义匹配"])

    get_github_client()  # 未登录直接提示并停止

    with st.container(border=True):
        query = st.text_input("搜索需求", key="star_query", placeholder=tr("star.query_ph"))
        top_n = st.slider("返回数量", 1, 10, 5, key="star_topn")
        if st.button(tr("star.search"), type="primary", use_container_width=True,
                     disabled=not query.strip(), key="star_search"):
            try:
                with st.spinner("正在检索 Star 仓库并语义匹配..."):
                    results = get_star_search_service().search(query, top_n=top_n)
                for i, item in enumerate(results, start=1):
                    repo = item["repo"]
                    with st.container(border=True):
                        head_l, head_r = st.columns([4, 1])
                        with head_l:
                            st.markdown(f"### {i:02d}. [{repo.full_name}]({repo.html_url})")
                        with head_r:
                            theme.score_badge(item["score"])
                        c1, c2 = st.columns(2)
                        c1.metric("Stars", theme.fmt_num(repo.stars))
                        c2.metric("语言", repo.language or "多语言")
                        if repo.description:
                            st.markdown(f"**简介** · {repo.description}")
                        st.caption(f"↳ 匹配理由：{item['reason']}")
            except Exception as exc:  # noqa: BLE001
                render_error(exc)
