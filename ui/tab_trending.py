# -*- coding: utf-8 -*-
"""Tab 3：🔥 中文热榜看板（0-Click 缓存秒开 + AI 简报 + 三列学习看板）。"""

from __future__ import annotations

import html
import importlib.util
import re
from datetime import datetime

import streamlit as st

from models import TrendingRepo
from ui import theme
from core.llm_summary import apply_compact_rules, apply_section_rules, format_stars, split_features
from ui.components import render_error
from ui.components import tr


# ---------------------------------------------------------------------------
# 0-Click：本地缓存读写（服务层已把抓取+AI 分析结果持久化到 data/trending_cache.json）
# ---------------------------------------------------------------------------
def _load_cache_into_session() -> bool:
    """从本地缓存恢复 items / 看板 / 技能雷达 / 简报（秒开，不发网络请求）。"""
    from services.trending_service import load_trending_cache

    cached = load_trending_cache()
    if not cached:
        return False
    st.session_state["trending_items"] = cached["items"]
    st.session_state["trending_board"] = cached["board"]
    st.session_state["trending_tags"] = cached["tags"]
    st.session_state["trending_briefing"] = cached["briefing"]
    st.session_state["trending_generated_at"] = cached.get("generated_at", "")
    return True


def _sync_board_from_cache() -> None:
    """把最新看板状态（本地）同步回 session_state，随后 rerun 重排三列。"""
    from services.trending_service import load_trending_cache

    cached = load_trending_cache()
    if cached:
        st.session_state["trending_board"] = cached["board"]


@st.fragment(run_every=15)
def _wait_for_preload_cache() -> None:
    """首次启动时等待后台预加载：每 15 秒重读本地缓存，出现后整页刷新。"""
    if _load_cache_into_session():
        st.rerun(scope="app")


def _refresh() -> None:
    """手动刷新：重新抓取 + AI 分析 + 写入缓存（保留原看板状态）。"""
    from services.trending_service import fetch_and_analyze_only

    progress = st.progress(0, text="准备中...")

    def on_progress(percent: int, message: str) -> None:
        progress.progress(percent / 100, text=message)

    result = fetch_and_analyze_only(progress_cb=on_progress)
    progress.empty()
    if not result.success:
        st.error(f"❌ {result.error}")
        return
    _load_cache_into_session()
    st.toast(tr("trending.refreshed").format(n=len(result.items)))


def _push_to_phone() -> None:
    """把当前榜单推送到手机（Ntfy），不触发 Notion。"""
    items = st.session_state.get("trending_items") or []
    if not items:
        st.warning(tr("trending.push_no_data"))
        return
    from services.trending_service import push_and_archive

    with st.spinner("正在推送手机..."):
        result = push_and_archive(items, do_push=True, do_archive=False)
    if not result.success:
        st.error(f"❌ {result.error}")
        return
    sent = result.pushed_channels.get("sent", 0) if result.pushed_channels else 0
    st.toast(tr("trending.push_ok").format(sent=sent, total=len(items)))
    st.success(tr("trending.push_done").format(sent=sent, total=len(items)))


# ---------------------------------------------------------------------------
# 顶栏：AI 技能雷达 + 30s 简报 + TTS 预留
# ---------------------------------------------------------------------------
def _tts_button(briefing: str) -> None:
    """语音播放按钮（预留 TTS 接口）：已安装 pyttsx3 则朗读，否则提示接入点。"""
    if st.button(tr("trending.tts"), key="trend_tts"):
        if importlib.util.find_spec("pyttsx3") is not None:
            try:
                import pyttsx3

                engine = pyttsx3.init()
                engine.say(briefing)
                engine.runAndWait()
                st.toast(tr("trending.tts_done"))
            except Exception as exc:  # noqa: BLE001
                st.warning(tr("trending.tts_fail").format(err=exc))
        else:
            st.toast(tr("trending.tts_missing"))


def _render_topbar(items: list, tags: list, briefing: str, generated_at: str) -> None:
    """顶部区域：缓存时间 + 推送/刷新 + 技能雷达 + 简报。"""
    top_l, top_m, top_r = st.columns([4, 1, 1])
    with top_l:
        if generated_at:
            st.caption(tr("trending.cache_at").format(time=generated_at))
        else:
            st.caption(tr("trending.cache_none"))
        try:
            age_hours = (datetime.now() - datetime.fromisoformat(generated_at)).total_seconds() / 3600
            if age_hours > 24:
                st.caption(tr("trending.stale"))
        except (ValueError, TypeError):
            pass
    with top_m:
        if st.button(tr("trending.push_phone"), key="trend_push_phone", help="Ntfy 推送到手机"):
            _push_to_phone()
    with top_r:
        if st.button(tr("trending.refresh"), key="trend_refresh", help="手动重新抓取 + AI 分析"):
            _refresh()

    if not items:
        return
    with st.container(border=True):
        st.markdown(f"**{tr('trending.radar')}**")
        theme.chips(tags or [], fallback=tr("trending.radar_fallback"))
        st.markdown(f"**{tr('trending.briefing')}**：{briefing or tr('trending.briefing_pending')}")
        _tts_button(briefing)


# ---------------------------------------------------------------------------
# 主区：对话式过滤 + Master-Detail（左侧列表 + 右侧大预览）
# ---------------------------------------------------------------------------
def _matches(repo: TrendingRepo, query: str) -> bool:
    """对话式过滤：多关键词（空格/逗号分隔）全部命中才保留。"""
    q = query.strip().lower()
    if not q:
        return True
    haystack = " ".join([
        repo.name, repo.description, repo.language, repo.zh_position,
        repo.zh_summary, repo.learning_points, " ".join(repo.tags),
    ]).lower()
    keywords = [kw for kw in re.split(r"[\s,，、;；]+", q) if kw]
    return all(kw in haystack for kw in keywords)


def _render_master_list(repos: list) -> None:
    """渲染左侧项目列表：名称单行 + 元数据小字（终端文件列表风格）。"""
    st.markdown('<span class="ghai-master-list" style="display:none;"></span>', unsafe_allow_html=True)
    st.markdown(f"**{tr('trending.count').format(n=len(repos))}**")
    if not repos:
        st.caption(tr("trending.empty_column"))
        return
    selected = st.session_state.get("selected_repo_index", 0)
    for idx, repo in enumerate(repos):
        is_selected = idx == selected
        prefix = "▸ " if is_selected else "  "
        if st.button(f"{prefix}{repo.name}", key=f"select_repo_{idx}", use_container_width=True):
            st.session_state["selected_repo_index"] = idx
            st.rerun()
        st.caption(
            f"★ {format_stars(repo.stars_total)} · {repo.language or tr('trending.multilang')}"
        )


def _badges_html(repo: TrendingRepo) -> str:
    """胶囊 Badge：语言 + 技术标签（GitHub Dark 配色）。"""
    # 组合语言与标签并去重（保留原始顺序），过滤空值
    raw_tags = [repo.language] + list(repo.tags or [])
    clean_tags = list(dict.fromkeys(t for t in raw_tags if t and str(t).strip()))[:4]
    escaped = [html.escape(str(t)) for t in clean_tags]
    return "".join(
        f'<span style="background: rgba(56,139,253,0.15); color:#58a6ff; '
        f'border-radius:12px; padding:3px 10px; font-size:12px; margin-right:6px; '
        f'display:inline-block; margin-bottom:6px;">{b}</span>'
        for b in escaped
    )


def _render_detail(repo: TrendingRepo | None) -> None:
    """右侧大预览：Header + 两行极简总结（≤35 字）+ 底部三个操作按钮。"""
    if repo is None:
        st.caption(tr("trending.select_hint"))
        return
    name = html.escape(repo.name)
    url = html.escape(repo.url)
    stars = format_stars(repo.stars_total)

    # 极简总结（≤35 字）：📌 定位 + 💡 亮点（旧缓存缺失时即时回退压缩）
    compact = apply_compact_rules({
        "position": (
            repo.compact_position or repo.zh_position
            or repo.overview or repo.description or "开源项目"
        ),
        "highlights": repo.compact_highlights or repo.features or split_features(repo),
    })
    compact_position = html.escape(compact["position"])
    compact_highlights = " / ".join(html.escape(h) for h in compact["highlights"])
    compact_html = (
        '<div style="border:1px solid #30363d; border-radius:8px; padding:10px 12px; '
        'margin-bottom:14px; background:#0d1117; color:#c9d1d9; font-size:14px; line-height:1.9;">'
        f'<b style="color:#e6edf3;">定位</b>　{compact_position}<br>'
        f'<b style="color:#e6edf3;">亮点</b>　{compact_highlights or "—"}'
        "</div>"
    )

    # 深度研读五板块（每条 ≤30 字，旧缓存缺失时即时压缩）
    sections = apply_section_rules({
        "overview": repo.overview or repo.zh_summary or repo.description or "—",
        "pain_points": repo.pain_points or "—",
        "features": repo.features or split_features(repo),
        "use_cases": repo.use_cases or "—",
        "tech_highlights": (
            repo.tech_highlights
            or f"{repo.language or 'Multi-language'} · {' '.join(repo.tags[:3])}"
        ),
    })
    section_html = ""
    section_titles = [
        (tr("trending.s_overview"), html.escape(sections["overview"]), None),
        (tr("trending.s_pain"), html.escape(sections["pain_points"]), None),
        (tr("trending.s_features"), None, [html.escape(f) for f in sections["features"]]),
        (tr("trending.s_use"), html.escape(sections["use_cases"]), None),
        (tr("trending.s_tech"), html.escape(sections["tech_highlights"]), None),
    ]
    for title, body, items in section_titles:
        section_html += (
            '<div style="margin-top:14px;">'
            f'<div style="color:#e6edf3; font-weight:700; font-size:14px; margin-bottom:6px;">{title}</div>'
        )
        if items is not None:
            section_html += '<ul style="margin:0; padding-left:20px;">' + "".join(
                f'<li style="color:#c9d1d9; font-size:13px; line-height:1.7; margin:3px 0;">{f}</li>'
                for f in items
            ) + "</ul>"
        else:
            section_html += (
                f'<div style="color:#c9d1d9; font-size:14px; line-height:1.8;">{body}</div>'
            )
        section_html += "</div>"

    with st.container(border=True):
        st.markdown(
            f"""
            <div class="ghai-detail-card">
              <div style="display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom:12px;">
                <a class="ghai-detail-title" href="{url}" target="_blank"
                   style="font-size:18px; font-weight:700; color:#58a6ff; text-decoration:none;
                          min-width:0; overflow-wrap:anywhere;">
                  {name}
                </a>
                <span style="color:#f0883e; font-size:14px; font-weight:600; white-space:nowrap; flex-shrink:0;">
                  ★ {stars}
                </span>
              </div>
              <div style="margin-bottom:14px;">{_badges_html(repo)}</div>
              {compact_html}
              {section_html}
            </div>
            """,
            unsafe_allow_html=True,
        )
        # 操作按钮随卡片状态变化：新榜可存入待学；待学/已归档可移回新榜
        current_status = (
            st.session_state.get("trending_board", {})
            .get(repo.name, {})
            .get("status", "new")
        )
        b1, b2, b3 = st.columns([1, 1, 1])
        with b1:
            st.link_button("打开 GitHub", repo.url, key=f"detail_open_{repo.name}")
        with b2:
            if current_status == "new":
                if st.button(tr("trending.plan"), use_container_width=True, key=f"detail_plan_{repo.name}"):
                    _set_status(repo.name, "planned")
            else:
                if st.button(tr("trending.restore"), use_container_width=True, key=f"detail_restore_{repo.name}"):
                    _set_status(repo.name, "new")
        with b3:
            if current_status == "archived":
                st.caption(tr("trending.archived_col"))
            elif st.button(tr("trending.archive"), use_container_width=True, key=f"detail_arch_{repo.name}"):
                _archive_to_notion(repo)


def _set_status(repo_name: str, status: str) -> None:
    """仅本地状态流转（存入待学 / 移回新榜），写入缓存并重排看板。"""
    from services.trending_service import update_card_status

    if update_card_status(repo_name, status):
        _sync_board_from_cache()
        st.toast(tr("trending.plan_toast") if status == "planned" else tr("trending.restore_toast"))
        st.rerun()
    else:
        st.error(tr("trending.status_update_fail"))


def _archive_to_notion(repo: TrendingRepo) -> None:
    """按需归档：点击才触发 Notion API，成功后把卡片移到「已归档」列。"""
    from core.notion_engine import NotionArchiver, NotionEngineError
    from services.trending_service import update_card_status

    archiver = NotionArchiver()
    if not archiver.configured:
        st.warning(tr("trending.archive_warn"))
        return
    with st.spinner(tr("trending.archive_spinner").format(name=repo.name)):
        try:
            url = archiver.archive_trending(repo)
        except NotionEngineError as exc:
            render_error(exc)
            return
    if update_card_status(repo.name, "archived", notion_url=url):
        _sync_board_from_cache()
        st.toast(tr("trending.archive_done").format(url=url))
        st.rerun()
    else:
        st.error(tr("trending.archive_state_fail"))


def render() -> None:
    """渲染中文热榜看板页面。"""
    # Master-Detail 样式（:has 精确命中热榜容器，不影响其他 Tab）
    st.markdown(
        """
        <style>
        .ghai-detail-title:hover {
            text-decoration: underline;
        }
        [data-testid="stVerticalBlockBorderWrapper"]:has(.ghai-detail-card) {
            background: #161b22 !important;
            border: 1px solid #30363d !important;
            border-radius: 12px;
            padding: 20px;
        }
        /* 左侧项目列表：名称单行省略 + 左对齐（终端文件列表风格） */
        [role="tabpanel"]:has(.ghai-master-list) button {
            justify-content: flex-start !important;
            text-align: left !important;
        }
        [role="tabpanel"]:has(.ghai-master-list) button > div,
        [role="tabpanel"]:has(.ghai-master-list) button p {
            display: block !important;
            width: 100% !important;
            margin: 0 !important;
            justify-content: flex-start !important;
            text-align: left !important;
        }
        [role="tabpanel"]:has(.ghai-master-list) button p {
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            font-family: var(--font-mono);
            font-size: 12.5px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    theme.section_header(
        "", tr("trending.title"), tr("trending.desc"),
    )
    theme.tagline([
        tr("trending.step_preload"),
        tr("trending.step_radar"),
        tr("trending.step_filter"),
        tr("trending.step_kanban"),
    ])

    # 0-Click：首次打开直接读缓存，不发网络请求
    if "trending_items" not in st.session_state:
        _load_cache_into_session()

    items = st.session_state.get("trending_items") or []
    board = st.session_state.get("trending_board") or {}
    tags = st.session_state.get("trending_tags") or []
    briefing = st.session_state.get("trending_briefing") or ""
    generated_at = st.session_state.get("trending_generated_at") or ""

    _render_topbar(items, tags, briefing, generated_at)

    if not items:
        theme.empty_state(
            "◌",
            tr("trending.empty_title"),
            tr("trending.empty_desc"),
        )
        _wait_for_preload_cache()  # 后台预加载完成后自动秒开，无需手动刷新
        if st.button(tr("trending.fetch_first"), type="primary", use_container_width=True, key="trend_fetch_first"):
            _refresh()
        return

    # 对话式过滤（实时）
    query = st.text_input(
        tr("trending.filter"),
        key="trend_query",
        placeholder=tr("trending.filter_ph"),
    )
    filtered = [repo for repo in items if _matches(repo, query)]
    if not filtered:
        st.info(tr("trending.no_match"))
        return

    if "selected_repo_index" not in st.session_state:
        st.session_state["selected_repo_index"] = 0

    # 顶部状态切换标签（今日新榜 / 计划学习 / 已归档）
    status_keys = ("new", "planned", "archived")
    counts = {
        s: sum(1 for r in filtered if board.get(r.name, {}).get("status", "new") == s)
        for s in status_keys
    }
    tab_labels = {
        "new": f"{tr('trending.new_col')} ({counts['new']})",
        "planned": f"{tr('trending.plan_col')} ({counts['planned']})",
        "archived": f"{tr('trending.archived_col')} ({counts['archived']})",
    }
    status_tab = st.radio(
        tr("trending.status_tab"),
        list(tab_labels.values()),
        horizontal=True,
        label_visibility="collapsed",
        key="trend_status_tab",
    )
    status = next(k for k, v in tab_labels.items() if v == status_tab)
    if st.session_state.get("trend_last_status", status) != status:
        st.session_state["selected_repo_index"] = 0
        st.session_state["trend_last_status"] = status

    status_items = [r for r in filtered if board.get(r.name, {}).get("status", "new") == status]
    if not status_items:
        st.info(tr("trending.empty_column"))
        return
    selected_index = st.session_state.get("selected_repo_index", 0)
    if selected_index >= len(status_items):
        selected_index = 0
        st.session_state["selected_repo_index"] = 0

    # Master-Detail：左侧列表 35% / 右侧大预览 65%
    left_col, right_col = st.columns([1, 1.8], gap="medium")
    with left_col:
        _render_master_list(status_items)
    with right_col:
        _render_detail(status_items[selected_index])
