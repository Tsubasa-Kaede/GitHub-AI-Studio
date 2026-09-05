# -*- coding: utf-8 -*-
"""
GitHub-AI-Studio · Streamlit 主入口
====================================

启动：streamlit run app.py

职责：渲染侧边栏配置，并在主区域挂载 6 大功能 Tab。
     所有业务逻辑委托 services 层，本文件只做路由。
"""

from __future__ import annotations

import streamlit as st

from ui import (
    components,
    tab_commit,
    tab_hosting,
    tab_release,
    tab_settings,
    tab_star,
    tab_trending,
    tab_worklog,
)
from ui import theme


def main() -> None:
    """应用主路由。"""
    st.set_page_config(
        page_title="GitHub-AI-Studio",
        page_icon="❯",
        layout="wide",
        initial_sidebar_state="expanded",
        menu_items={
            "Get help": None,
            "Report a bug": None,
            "About": "GitHub-AI-Studio · 本地 GitHub 智能化管理控制台\n"
                     "凭证仅存本地 .env，不会上传。",
        },
    )

    # 注入全局设计系统 + 品牌条（唯一记忆点：终端风控制台）
    theme.inject_global_styles()
    theme.render_brand_header()

    # 侧边栏：登录状态 + 凭证设置 + 个人偏好
    components.render_sidebar()

    # 主面板：7 大功能 Tab（胶囊导航，标题随界面语言切换）
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(
        [
            components.tr("nav.tab_hosting"),
            components.tr("nav.tab_commit"),
            "🔥 中文热榜",  # 热榜版块保持中文，不参与双语切换
            components.tr("nav.tab_release"),
            components.tr("nav.tab_star"),
            components.tr("nav.tab_worklog"),
            components.tr("nav.tab_settings"),
        ]
    )
    with tab1:
        tab_hosting.render()
    with tab2:
        tab_commit.render()
    with tab3:
        tab_trending.render()
    with tab4:
        tab_release.render()
    with tab5:
        tab_star.render()
    with tab6:
        tab_worklog.render()
    with tab7:
        tab_settings.render()

    st.divider()
    footer_text = components.tr("app.footer")
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:8px;opacity:.72;
                    font-family:var(--font-mono);font-size:11px;color:var(--text-3);">
          <span>❯ ghai --studio</span><span>·</span>
          <span>{footer_text}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
