# -*- coding: utf-8 -*-
"""
GitHub-AI-Studio 视觉设计系统
=============================

设计方向：「本地开发者指挥台」
    - 深空蓝黑底色 + 单一克制的主色，无渐变、无光晕、无多余动效；
    - 终端风品牌条（`❯ ghai --studio` + 状态点）作为全局记忆点；
    - 数据型内容统一使用等宽字体，营造「控制台」质感；
    - 装饰只保留层级必需的边框与表面色差，信息密度优先；
    - 遵守可访问性：焦点可见、足够对比度、尊重 reduced-motion。

本模块只负责「视觉层」，不包含任何业务逻辑，所有 Tab 页均可复用。
"""

from __future__ import annotations

import html

import streamlit as st

# ---------------------------------------------------------------------------
# 设计令牌（Design Tokens）
# ---------------------------------------------------------------------------
COLORS = {
    "bg_deep": "#070B12",          # 全局背景（深空蓝黑）
    "bg": "#0A0F1A",               # 主背景
    "surface": "#101726",          # 卡片 / 输入框表面
    "surface_2": "#182137",        # 悬停 / 抬升表面
    "border": "rgba(151, 167, 201, 0.14)",
    "primary": "#4A8AF4",          # 主色（克制的工作台蓝）
    "primary_hi": "#6FA3F8",       # 主色高亮
    "accent": "#4A8AF4",           # 点缀色（与主色统一，减少色相数）
    "success": "#34D399",
    "warning": "#FBBF24",
    "danger": "#F87171",
    "text": "#E8ECF5",
    "text_2": "#A6B0C8",
    "text_3": "#6E7A94",
}

FONT_BODY = (
    '-apple-system, "Segoe UI Variable", "Segoe UI", '
    '"Microsoft YaHei UI", "PingFang SC", "Inter", sans-serif'
)
FONT_MONO = '"JetBrains Mono", "Cascadia Code", Consolas, "SFMono-Regular", monospace'


def esc(value: object) -> str:
    """转义用户可控文本，避免注入 HTML。"""
    return html.escape(str(value), quote=True)


def fmt_num(num: int | None) -> str:
    """把大数字格式化为 56.2k / 1.3M（控制台式紧凑数字）。"""
    num = num or 0
    if num >= 1_000_000:
        return f"{num / 1_000_000:.1f}M"
    if num >= 1_000:
        return f"{num / 1_000:.1f}k"
    return str(num)


# ---------------------------------------------------------------------------
# 全局 CSS（注入 Streamlit 阴影 DOM）
# ---------------------------------------------------------------------------
CSS = """
<style>
[data-testid="stAppViewContainer"] {
    --bg-deep: #070B12;
    --bg: #0A0F1A;
    --surface: #101726;
    --surface-2: #182137;
    --border: rgba(151, 167, 201, 0.14);
    --primary: #4A8AF4;
    --primary-hi: #6FA3F8;
    --accent: #4A8AF4;
    --success: #34D399;
    --warning: #FBBF24;
    --danger: #F87171;
    --text: #E8ECF5;
    --text-2: #A6B0C8;
    --text-3: #6E7A94;
    --font-body: -apple-system, "Segoe UI Variable", "Segoe UI",
        "Microsoft YaHei UI", "PingFang SC", "Inter", sans-serif;
    --font-mono: "JetBrains Mono", "Cascadia Code", Consolas,
        "SFMono-Regular", monospace;

    color: var(--text);
    font-family: var(--font-body);
    background: var(--bg-deep);
}

/* ---------- 全局框架 ---------- */
[data-testid="stHeader"] {
    background: transparent;
}
/* 隐藏 Streamlit 原生 Deploy / 主菜单工具栏（与应用无关的原生元素） */
[data-testid="stHeader"] [data-testid="stToolbar"] {
    display: none !important;
}
[data-testid="stMainBlockContainer"] {
    max-width: 1200px;
    padding-top: 1.1rem;
    padding-bottom: 3rem;
}
[data-testid="stSidebar"] {
    background: #0B101B;
    border-right: 1px solid var(--border);
}
[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
    padding-top: 1.1rem;
}

/* ---------- 品牌条 ---------- */
.ghai-brand {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding: 6px 4px 18px 4px;
}
.ghai-brand-left {
    display: flex;
    align-items: center;
    gap: 14px;
    min-width: 0;
}
.ghai-brand-mark {
    flex: 0 0 auto;
    width: 44px;
    height: 44px;
    border-radius: 10px;
    display: grid;
    place-items: center;
    font-family: var(--font-mono);
    font-weight: 800;
    font-size: 19px;
    color: var(--primary);
    background: var(--surface);
    border: 1px solid var(--border);
}
.ghai-brand-title {
    font-size: 20px;
    font-weight: 750;
    letter-spacing: 0.2px;
    line-height: 1.2;
    color: var(--text);
}
.ghai-brand-sub {
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--text-3);
    margin-top: 4px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.ghai-live {
    flex: 0 0 auto;
    display: inline-flex;
    align-items: center;
    gap: 7px;
    font-family: var(--font-mono);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
    color: var(--success);
    border-radius: 6px;
    padding: 5px 11px;
}
.ghai-live .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--success);
}
.ghai-hairline {
    height: 1px;
    margin: 0 0 20px 0;
    background: var(--border);
}

/* ---------- 页头 / 章节标题 ---------- */
.ghai-section {
    display: flex;
    align-items: baseline;
    gap: 10px;
    margin: 4px 0 2px 0;
}
.ghai-section-prefix {
    font-family: var(--font-mono);
    font-size: 13px;
    font-weight: 700;
    color: var(--primary);
}
.ghai-section-title {
    font-size: 21px;
    font-weight: 750;
    color: var(--text);
    line-height: 1.25;
}
.ghai-section-desc {
    font-size: 13px;
    color: var(--text-3);
    margin: 4px 0 14px 2px;
    line-height: 1.55;
}

/* ---------- Tab（分组分段，不再是胶囊） ---------- */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    gap: 2px;
    width: fit-content;
    max-width: 100%;
    background: transparent;
    border: none;
    border-bottom: 1px solid var(--border);
    border-radius: 0;
    padding: 0;
    margin-bottom: 18px;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
    border-radius: 6px 6px 0 0;
    padding: 8px 14px;
    color: var(--text-3);
    font-weight: 600;
    font-size: 13px;
    border-bottom: 2px solid transparent;
    transition: color 0.15s ease;
}
[data-testid="stTabs"] [data-baseweb="tab"]:hover {
    color: var(--text);
    background: transparent;
}
[data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"] {
    color: var(--text);
    background: transparent;
    border-bottom: 2px solid var(--primary);
    box-shadow: none;
}

/* ---------- 卡片（st.container border / st.metric） ---------- */
[data-testid="stVerticalBlockBorderWrapper"] {
    background: var(--surface);
    border: 1px solid var(--border) !important;
    border-radius: 10px;
    transition: border-color 0.16s ease;
}
[data-testid="stVerticalBlockBorderWrapper"]:hover {
    border-color: rgba(151, 167, 201, 0.26) !important;
}

[data-testid="stMetric"] {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 12px 14px;
}
[data-testid="stMetricLabel"] {
    color: var(--text-3);
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.4px;
}
[data-testid="stMetricValue"] {
    font-family: var(--font-mono);
    font-size: 24px;
    font-weight: 700;
    color: var(--text);
}
[data-testid="stMetricDelta"] {
    font-family: var(--font-mono);
    font-size: 12px;
}

/* ---------- 按钮层级 ---------- */
.stButton > button,
[data-testid="stFormSubmitButton"] > button,
[data-testid="stDownloadButton"] > button,
[data-testid="stBaseButton-secondary"] button,
[data-testid="stLinkButton"] {
    border-radius: 8px;
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--text-2);
    font-weight: 600;
    font-size: 13.5px;
    transition: all 0.15s ease;
}
.stButton > button:hover,
[data-testid="stFormSubmitButton"] > button:hover,
[data-testid="stDownloadButton"] > button:hover,
[data-testid="stBaseButton-secondary"] button:hover,
[data-testid="stLinkButton"]:hover {
    border-color: rgba(151, 167, 201, 0.30);
    color: var(--text);
    background: var(--surface-2);
}

[data-testid="stBaseButton-primary"] button,
[data-testid="stBaseButton-primaryFormSubmit"] button,
.stButton > button[kind="primary"] {
    background: var(--primary) !important;
    border: none !important;
    color: #fff !important;
    font-weight: 650;
}
[data-testid="stBaseButton-primary"] button:hover,
[data-testid="stBaseButton-primaryFormSubmit"] button:hover,
.stButton > button[kind="primary"]:hover {
    background: var(--primary-hi) !important;
    box-shadow: none;
}

/* ---------- 输入控件 ---------- */
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
[data-testid="stNumberInput"] input,
[data-testid="stSelectbox"] [data-baseweb="select"] > div,
[data-testid="stMultiSelect"] [data-baseweb="select"] > div {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: 10px !important;
    color: var(--text) !important;
    caret-color: var(--primary);
}
[data-testid="stTextInput"] input:focus,
[data-testid="stTextArea"] textarea:focus,
[data-testid="stNumberInput"] input:focus {
    border-color: rgba(74, 138, 244, 0.55) !important;
    box-shadow: 0 0 0 2px rgba(74, 138, 244, 0.15) !important;
}
[data-testid="stTextInput"] label,
[data-testid="stTextArea"] label,
[data-testid="stNumberInput"] label,
[data-testid="stSelectbox"] label,
[data-testid="stRadio"] label,
[data-testid="stCheckbox"] label {
    color: var(--text-2);
    font-size: 13px;
    font-weight: 600;
}
[data-testid="stRadio"] [role="radiogroup"] {
    gap: 6px;
}
[data-testid="stRadio"] label {
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 4px 12px;
    background: var(--surface);
}
[data-testid="stCheckbox"] input {
    accent-color: var(--primary);
}
[data-testid="stSlider"] [data-testid="stSliderThumbValue"] {
    color: var(--primary);
}

/* ---------- 进度条 ---------- */
[data-testid="stProgress"] > div {
    height: 7px;
    border-radius: 999px;
    background: rgba(151, 167, 201, 0.10);
}
[data-testid="stProgress"] [role="progressbar"] > div > div > div {
    background: var(--primary);
    border-radius: 999px;
}

/* ---------- 提示 / 展开 / 分隔线 ---------- */
[data-testid="stAlert"] {
    border-radius: 12px;
    border: 1px solid var(--border);
    padding: 4px 6px;
}
[data-testid="stExpander"] details {
    border: 1px solid var(--border);
    border-radius: 12px;
    background: rgba(16, 23, 38, 0.65);
}
[data-testid="stExpander"] summary {
    color: var(--text-2);
    font-weight: 600;
}
[data-testid="stDivider"] {
    border-color: var(--border);
}
[data-testid="stCaptionContainer"] {
    color: var(--text-3);
}
[data-testid="stCodeBlock"] {
    background: #0C111D;
    border: 1px solid var(--border);
    border-radius: 12px;
    font-family: var(--font-mono);
}

/* ---------- 自定义小组件 ---------- */
.ghai-status-card {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 14px;
    border-radius: 10px;
    border: 1px solid var(--border);
    background: var(--surface);
    margin: 2px 0 10px 0;
}
.ghai-status-card.warn {
    border-color: rgba(251, 191, 36, 0.30);
}
.ghai-status-avatar {
    flex: 0 0 auto;
    width: 38px;
    height: 38px;
    border-radius: 9px;
    display: grid;
    place-items: center;
    font-family: var(--font-mono);
    font-weight: 800;
    font-size: 16px;
    color: var(--text-2);
    background: var(--surface-2);
    border: 1px solid var(--border);
}
.ghai-status-body {
    min-width: 0;
    flex: 1;
}
.ghai-status-name {
    font-size: 14px;
    font-weight: 700;
    color: var(--text);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.ghai-status-meta {
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--text-3);
    margin-top: 3px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.ghai-badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 11px;
    font-weight: 700;
    border-radius: 999px;
    padding: 3px 9px;
    font-family: var(--font-mono);
}
.ghai-badge.ok {
    color: var(--success);
    background: rgba(52, 211, 153, 0.10);
    border: 1px solid rgba(52, 211, 153, 0.28);
}
.ghai-badge.warn {
    color: var(--warning);
    background: rgba(251, 191, 36, 0.10);
    border: 1px solid rgba(251, 191, 36, 0.30);
}
.ghai-badge.err {
    color: var(--danger);
    background: rgba(248, 113, 113, 0.10);
    border: 1px solid rgba(248, 113, 113, 0.30);
}
.ghai-chip {
    display: inline-flex;
    align-items: center;
    font-family: var(--font-mono);
    font-size: 11px;
    font-weight: 600;
    color: var(--text-2);
    background: rgba(151, 167, 201, 0.08);
    border: 1px solid rgba(151, 167, 201, 0.20);
    border-radius: 6px;
    padding: 3px 9px;
    margin: 0 6px 6px 0;
}
.ghai-score {
    display: inline-flex;
    align-items: center;
    font-family: var(--font-mono);
    font-size: 12px;
    font-weight: 700;
    color: var(--text-2);
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 3px 9px;
}
.ghai-empty {
    text-align: center;
    padding: 44px 20px;
    border: 1px dashed rgba(151, 167, 201, 0.24);
    border-radius: 10px;
    background: transparent;
}
.ghai-empty-icon {
    font-size: 26px;
    margin-bottom: 10px;
    color: var(--text-3);
}
.ghai-empty-title {
    font-size: 15px;
    font-weight: 700;
    color: var(--text-2);
}
.ghai-empty-desc {
    font-size: 12.5px;
    color: var(--text-3);
    margin-top: 6px;
}
.ghai-step-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 2px 0 14px 0;
}
.ghai-step {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    font-family: var(--font-mono);
    font-size: 11px;
    font-weight: 700;
    color: var(--text-3);
    background: rgba(16, 23, 38, 0.8);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 5px 11px;
}
.ghai-step .n {
    color: var(--primary);
}
.ghai-step.active {
    color: var(--text);
    border-color: rgba(74, 138, 244, 0.40);
    background: rgba(74, 138, 244, 0.08);
}
.ghai-tagline {
    display: flex;
    align-items: center;
    gap: 8px;
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--text-3);
    margin: 2px 0 16px 0;
}
.ghai-tagline code {
    color: var(--text-2);
    background: rgba(151, 167, 201, 0.07);
    border: 1px solid rgba(151, 167, 201, 0.18);
    border-radius: 5px;
    padding: 1px 7px;
    font-size: 11.5px;
}

/* ---------- 可访问性 ---------- */
button:focus-visible,
input:focus-visible,
textarea:focus-visible,
[role="tab"]:focus-visible,
a:focus-visible {
    outline: 2px solid var(--primary) !important;
    outline-offset: 2px;
}
@media (prefers-reduced-motion: reduce) {
    * {
        animation: none !important;
        transition: none !important;
    }
}

/* ---------- 滚动条 ---------- */
::-webkit-scrollbar {
    width: 9px;
    height: 9px;
}
::-webkit-scrollbar-thumb {
    background: rgba(151, 167, 201, 0.22);
    border-radius: 999px;
}
::-webkit-scrollbar-thumb:hover {
    background: rgba(151, 167, 201, 0.36);
}
::-webkit-scrollbar-track {
    background: transparent;
}
</style>
"""


# ---------------------------------------------------------------------------
# 渲染辅助
# ---------------------------------------------------------------------------
def inject_global_styles() -> None:
    """向 Streamlit 阴影 DOM 注入全局设计系统样式。"""
    st.markdown(CSS, unsafe_allow_html=True)


def render_brand_header() -> None:
    """渲染全局品牌条：终端风 logo + 标题 + 本地实时状态点。"""
    st.markdown(
        """
        <div class="ghai-brand">
          <div class="ghai-brand-left">
            <div class="ghai-brand-mark">❯</div>
            <div>
              <div class="ghai-brand-title">GitHub-AI-Studio</div>
              <div class="ghai-brand-sub">ghai --studio · 本地 GitHub 智能化管理控制台</div>
            </div>
          </div>
          <span class="ghai-live"><i class="dot"></i>LOCAL</span>
        </div>
        <div class="ghai-hairline"></div>
        """,
        unsafe_allow_html=True,
    )


def section_header(icon: str, title: str, desc: str = "") -> None:
    """统一章节标题：终端前缀 + 标题 + 说明（icon 可空，保持克制）。"""
    prefix = f"{esc(icon)} " if icon else ""
    st.markdown(
        f"""
        <div class="ghai-section">
          <span class="ghai-section-prefix">#</span>
          <span class="ghai-section-title">{prefix}{esc(title)}</span>
        </div>
        <div class="ghai-section-desc">{esc(desc)}</div>
        """,
        unsafe_allow_html=True,
    )


def tagline(parts: list[str]) -> None:
    """终端风流程说明，如：读取 Diff → 安全扫描 → AI 生成 → 一键推送。"""
    body = " → ".join(f"<code>{esc(part)}</code>" for part in parts)
    st.markdown(f'<div class="ghai-tagline">❯ {body}</div>', unsafe_allow_html=True)


def empty_state(icon: str, title: str, desc: str) -> None:
    """空状态引导面板：邀请用户行动，而不是展示冷冰冰的提示。"""
    st.markdown(
        f"""
        <div class="ghai-empty">
          <div class="ghai-empty-icon">{esc(icon)}</div>
          <div class="ghai-empty-title">{esc(title)}</div>
          <div class="ghai-empty-desc">{esc(desc)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_badge(text: str, tone: str = "ok") -> None:
    """小徽章：ok / warn / err 三种语义色。"""
    st.markdown(
        f'<span class="ghai-badge {esc(tone)}">{esc(text)}</span>',
        unsafe_allow_html=True,
    )


def chips(items: list[str], fallback: str = "多语言") -> None:
    """技术标签胶囊组（英文专有名词原样显示）。"""
    items = [i for i in items if i]
    if not items:
        items = [fallback]
    body = "".join(f'<span class="ghai-chip">{esc(tag)}</span>' for tag in items)
    st.markdown(f'<div style="margin: 2px 0 8px 0;">{body}</div>', unsafe_allow_html=True)


def score_badge(score: float | int | None) -> None:
    """热榜匹配度徽章（9.5/10）。"""
    text = f"{score:.1f}/10" if score is not None else "-"
    st.markdown(f'<span class="ghai-score">{esc(text)}</span>', unsafe_allow_html=True)


def sidebar_status_card(
    login: str | None, source: str | None, ok: bool, error: str | None = None
) -> None:
    """侧边栏 GitHub 登录状态卡片（头像首字母 + 来源 + 错误摘要）。"""
    if ok and login:
        tone, title, meta = "ok", login, f"凭证来源 · {source or 'unknown'}"
        avatar = esc(login[:1].upper())
    else:
        tone, title = "warn", "未连接 GitHub"
        meta = (error or "请检查 Token / 网络 / 代理")[:42]
        avatar = "○"  # 空心圆：未连接（区别于登录态的首字母头像）
    st.markdown(
        f"""
        <div class="ghai-status-card {tone}">
          <div class="ghai-status-avatar">{avatar}</div>
          <div class="ghai-status-body">
            <div class="ghai-status-name">{esc(title)}</div>
            <div class="ghai-status-meta">{esc(meta)}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
