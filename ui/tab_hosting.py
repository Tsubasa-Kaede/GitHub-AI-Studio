# -*- coding: utf-8 -*-
"""Tab 1：🚀 一键项目托管视图。"""

from __future__ import annotations

import streamlit as st

from ui.components import get_github_client, get_hosting_service, render_error, tr
from ui import theme


def render() -> None:
    """渲染一键托管页面。"""
    theme.section_header("🚀", tr("hosting.title"), tr("hosting.desc"))
    theme.tagline(["选择目录", "AI README", "GitHub 建仓", "Commit & Push"])

    get_github_client()  # 未登录直接提示并停止

    with st.container(border=True):
        # 流程步骤提示（第 1 步为当前）
        st.markdown(
            """
            <div class="ghai-step-row">
              <span class="ghai-step active"><span class="n">01</span> 本地目录</span>
              <span class="ghai-step"><span class="n">02</span> 仓库设置</span>
              <span class="ghai-step"><span class="n">03</span> AI README</span>
              <span class="ghai-step"><span class="n">04</span> 发布</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        col1, col2 = st.columns([3, 2])
        with col1:
            path = st.text_input(
                "📁 本地项目目录（绝对路径）", placeholder="C:\\Users\\you\\my-project", key="host_path"
            )
            repo_name = st.text_input("📦 远程仓库名", placeholder="my-awesome-project", key="host_repo_name",
                                      help="留空则使用目录名")
        with col2:
            visibility = st.radio("可见性", ["private", "public"], horizontal=True, key="host_visibility")
            description = st.text_input("仓库描述", placeholder="可选", key="host_description")
            use_ai_readme = st.checkbox("AI 生成 README.md", value=True, key="host_ai_readme")
            languages = st.text_input(
                "多语言 README（逗号分隔）", value="zh-CN,en", key="host_langs",
                help="例如 zh-CN,en,ja：生成 README.md / README.en.md / README.ja.md",
            )
            force = st.checkbox("强制模式（跳过敏感扫描/覆盖 README）", value=False, key="host_force")

        if st.button(tr("hosting.run"), type="primary", use_container_width=True,
                     disabled=not path, key="host_run"):
            if not repo_name:
                repo_name = path.rstrip("\\/").split("\\")[-1].split("/")[-1]
            progress = st.progress(0, text="准备中...")

            def on_progress(percent: int, message: str) -> None:
                progress.progress(percent / 100, text=message)

            try:
                langs = [x.strip() for x in languages.split(",") if x.strip()] or ["zh-CN", "en"]
                result = get_hosting_service().run(
                    path=path, repo_name=repo_name, visibility=visibility,
                    description=description, use_ai_readme=use_ai_readme,
                    readme_languages=langs, force=force,
                    progress_cb=on_progress,
                )
                st.success("🎉 托管成功！")
                st.markdown(f"🔗 **仓库地址**：{result.repo_url}")
                col_a, col_b, col_c = st.columns(3)
                col_a.metric("分支", result.branch)
                col_b.metric("提交", result.commit_sha[:7])
                col_c.metric("AI README", "已生成" if result.readme_generated else "保留原文件")
            except Exception as exc:  # noqa: BLE001
                progress.empty()
                render_error(exc)
