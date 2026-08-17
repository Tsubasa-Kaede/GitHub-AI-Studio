# -*- coding: utf-8 -*-
"""
GitHub-AI-Studio 视觉设计系统
=============================

设计方向：「本地开发者指挥台」
    - 深空蓝黑底色 + 柔和紫色主色 + 青色点缀（AI 活性/成功信号）；
    - 终端风品牌条（`❯ ghai --studio` + 实时状态点）作为全局记忆点；
    - 数据型内容统一使用等宽字体，营造「控制台」质感；
    - 卡片圆角、胶囊 Tab、主次分明的按钮层级；
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
    "primary": "#8B7CFF",          # 主紫
    "primary_hi": "#A78BFA",       # 主紫高亮
    "accent": "#22D3EE",           # 青色点缀（AI / 在线）
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
    --primary: #8B7CFF;
    --primary-hi: #A78BFA;
    --accent: #22D3EE;
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
    background:
        radial-gradient(1100px 460px at 88% -8%, rgba(139, 124, 255, 0.10), transparent 60%),
        radial-gradient(900px 420px at -8% 8%, rgba(34, 211, 238, 0.05), transparent 55%),
        var(--bg-deep);
}

/* ---------- 全局框架 ---------- */
[data-testid="stHeader"] {
    background: transparent;
}
[data-testid="stMainBlockContainer"] {
    max-width: 1200px;
    padding-top: 1.1rem;
    padding-bottom: 3rem;
}
[data-testid="stSidebar"] {
    background:
        linear-gradient(180deg, rgba(16, 23, 38, 0.96), rgba(10, 15, 26, 0.98));
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
    width: 46px;
    height: 46px;
    border-radius: 14px;
    display: grid;
    place-items: center;
    font-family: var(--font-mono);
    font-weight: 800;
    font-size: 20px;
    color: #fff;
    background:
        linear-gradient(145deg, rgba(139, 124, 255, 0.95), rgba(99, 102, 241, 0.9));
    box-shadow:
        0 6px 22px rgba(139, 124, 255, 0.35),
        inset 0 1px 0 rgba(255, 255, 255, 0.25);
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
    background: rgba(52, 211, 153, 0.09);
    border: 1px solid rgba(52, 211, 153, 0.28);
    border-radius: 999px;
    padding: 5px 11px;
}
.ghai-live .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--success);
    box-shadow: 0 0 0 0 rgba(52, 211, 153, 0.55);
    animation: ghai-pulse 2.4s ease-out infinite;
}
@keyframes ghai-pulse {
    0% { box-shadow: 0 0 0 0 rgba(52, 211, 153, 0.45); }
    70% { box-shadow: 0 0 0 7px rgba(52, 211, 153, 0); }
    100% { box-shadow: 0 0 0 0 rgba(52, 211, 153, 0); }
}
.ghai-hairline {
    height: 1px;
    margin: 0 0 20px 0;
    background: linear-gradient(
        90deg,
        rgba(139, 124, 255, 0.55),
        rgba(34, 211, 238, 0.18),
        transparent
    );
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

/* ---------- 胶囊 Tab ---------- */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    gap: 6px;
    width: fit-content;
    max-width: 100%;
    background: rgba(16, 23, 38, 0.72);
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 5px;
    margin-bottom: 18px;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
    border-radius: 999px;
    padding: 7px 15px;
    color: var(--text-2);
    font-weight: 600;
    font-size: 13px;
    transition: color 0.15s ease, background 0.15s ease;
}
[data-testid="stTabs"] [data-baseweb="tab"]:hover {
    color: var(--text);
    background: rgba(139, 124, 255, 0.10);
}
[data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"] {
    color: #fff;
    background: linear-gradient(135deg, rgba(139, 124, 255, 0.95), rgba(109, 93, 246, 0.95));
    box-shadow: 0 4px 14px rgba(139, 124, 255, 0.30);
}

/* ---------- 卡片（st.container border / st.metric） ---------- */
[data-testid="stVerticalBlockBorderWrapper"] {
    background: linear-gradient(180deg, rgba(16, 23, 38, 0.92), rgba(13, 19, 33, 0.92));
    border: 1px solid var(--border) !important;
    border-radius: 14px;
    box-shadow: 0 1px 0 rgba(255, 255, 255, 0.03) inset;
    transition: border-color 0.16s ease, transform 0.16s ease, box-shadow 0.16s ease;
}
[data-testid="stVerticalBlockBorderWrapper"]:hover {
    border-color: rgba(139, 124, 255, 0.38) !important;
    box-shadow: 0 8px 28px rgba(7, 11, 18, 0.45);
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
    border-radius: 10px;
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
    border-color: rgba(139, 124, 255, 0.45);
    color: var(--text);
    background: var(--surface-2);
}

[data-testid="stBaseButton-primary"] button,
[data-testid="stBaseButton-primaryFormSubmit"] button,
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #8B7CFF, #6D5DF6) !important;
    border: none !important;
    color: #fff !important;
    font-weight: 700;
    box-shadow: 0 5px 18px rgba(139, 124, 255, 0.28);
}
[data-testid="stBaseButton-primary"] button:hover,
[data-testid="stBaseButton-primaryFormSubmit"] button:hover,
.stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg, #A78BFA, #7C6CF8) !important;
    box-shadow: 0 7px 24px rgba(139, 124, 255, 0.38);
    transform: translateY(-1px);
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
    border-color: rgba(139, 124, 255, 0.65) !important;
    box-shadow: 0 0 0 3px rgba(139, 124, 255, 0.14) !important;
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
    border-radius: 999px;
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
    background: linear-gradient(90deg, #8B7CFF, #22D3EE);
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
    border-radius: 14px;
    border: 1px solid var(--border);
    background: linear-gradient(180deg, rgba(16, 23, 38, 0.95), rgba(13, 19, 33, 0.95));
    margin: 2px 0 10px 0;
}
.ghai-status-card.warn {
    border-color: rgba(251, 191, 36, 0.35);
}
.ghai-status-avatar {
    flex: 0 0 auto;
    width: 38px;
    height: 38px;
    border-radius: 11px;
    display: grid;
    place-items: center;
    font-family: var(--font-mono);
    font-weight: 800;
    font-size: 17px;
    color: #fff;
    background: linear-gradient(145deg, rgba(139, 124, 255, 0.9), rgba(34, 211, 238, 0.65));
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
    background: rgba(139, 124, 255, 0.10);
    border: 1px solid rgba(139, 124, 255, 0.25);
    border-radius: 999px;
    padding: 3px 10px;
    margin: 0 6px 6px 0;
}
.ghai-score {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-family: var(--font-mono);
    font-size: 12px;
    font-weight: 800;
    color: #fff;
    background: linear-gradient(135deg, rgba(139, 124, 255, 0.9), rgba(109, 93, 246, 0.9));
    border-radius: 999px;
    padding: 3px 11px;
    box-shadow: 0 3px 12px rgba(139, 124, 255, 0.25);
}
.ghai-empty {
    text-align: center;
    padding: 44px 20px;
    border: 1px dashed rgba(151, 167, 201, 0.28);
    border-radius: 16px;
    background: rgba(16, 23, 38, 0.45);
}
.ghai-empty-icon {
    font-size: 34px;
    margin-bottom: 10px;
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
    border-radius: 999px;
    padding: 5px 12px;
}
.ghai-step .n {
    color: var(--primary);
}
.ghai-step.active {
    color: var(--text);
    border-color: rgba(139, 124, 255, 0.45);
    background: rgba(139, 124, 255, 0.10);
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
    color: var(--accent);
    background: rgba(34, 211, 238, 0.08);
    border: 1px solid rgba(34, 211, 238, 0.22);
    border-radius: 6px;
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
    """统一章节标题：终端前缀 + 标题 + 说明。"""
    st.markdown(
        f"""
        <div class="ghai-section">
          <span class="ghai-section-prefix">#</span>
          <span class="ghai-section-title">{esc(icon)} {esc(title)}</span>
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
    st.markdown(f'<span class="ghai-score">🔥 {esc(text)}</span>', unsafe_allow_html=True)


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
        avatar = "?"
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
