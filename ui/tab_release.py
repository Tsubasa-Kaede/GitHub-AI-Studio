# -*- coding: utf-8 -*-
"""Tab 4：📦 AI 自动发版视图（CHANGELOG 预览 + 一键发布 Release）。"""

from __future__ import annotations

import streamlit as st

from ui.components import get_github_client, get_release_service, render_error, tr
from ui import theme


def render() -> None:
    """渲染发版页面。"""
    theme.section_header("", tr("release.title"), tr("release.desc"))
    theme.tagline(["读取 Git Log", "AI 分类", "预览编辑", "发布 Release"])

    get_github_client()

    with st.container(border=True):
        col1, col2 = st.columns(2)
        with col1:
            repo_path = st.text_input(
                "本地 Git 仓库目录", placeholder="C:\\Users\\you\\my-project", key="release_repo_path"
            )
            tag = st.text_input("版本 Tag", placeholder="v1.2.0", key="release_tag")
        with col2:
            st.text_input("GitHub 仓库全名", placeholder="owner/repo", key="release_full_name")
            st.caption("Release 将发布到该远程仓库")

        if st.button(tr("release.generate"), type="primary", use_container_width=True,
                     disabled=not (repo_path and tag), key="release_generate"):
            try:
                info = get_release_service().generate(repo_path=repo_path, tag=tag)
                st.session_state["release_info"] = info
                st.session_state["release_changelog_editor"] = info.changelog
            except Exception as exc:  # noqa: BLE001
                render_error(exc)

    info = st.session_state.get("release_info")
    if info is not None:
        with st.container(border=True):
            c1, c2, c3 = st.columns(3)
            c1.metric("提交数", info.commits_count)
            c2.metric("版本", info.tag)
            c3.metric("对比上一版", info.previous_tag or "-")
            st.text_area(
                "CHANGELOG（可编辑后发布）", value=info.changelog,
                height=320, key="release_changelog_editor",
            )
            if st.button(tr("release.publish"), type="primary", use_container_width=True, key="release_publish"):
                if not st.session_state.get("release_full_name"):
                    st.error("请填写 GitHub 仓库全名。")
                    return
                try:
                    result = get_release_service().publish(
                        st.session_state["release_full_name"], info,
                        body=st.session_state.get("release_changelog_editor", info.changelog),
                    )
                    st.success(f"✓ Release 已发布：{result['url']}")
                except Exception as exc:  # noqa: BLE001
                    render_error(exc)
