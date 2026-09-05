# -*- coding: utf-8 -*-
"""
Streamlit 公共组件
===================

1. 侧边栏：GitHub 登录状态卡片 + 凭证设置面板 + 个人偏好
2. 错误渲染与 GitHub 客户端获取等公共工具
"""

from __future__ import annotations

import datetime

import streamlit as st

import config
from core import app_config
from core.i18n import translate as _i18n_translate
from config import ConfigError, settings, update_env_file
from ui import theme


def tr(key: str) -> str:
    """按当前界面语言取文案（会话优先，回退 data/config.json）。"""
    lang = st.session_state.get("lang") or app_config.get_language()
    return _i18n_translate(key, lang)


@st.cache_resource(ttl=3600, show_spinner=False)
def _cached_client():
    """缓存 GitHub 客户端实例（避免每次交互都重新初始化 PyGithub）。"""
    from core.github_client import GitHubClient

    return GitHubClient()


@st.cache_resource(ttl=3600, show_spinner=False)
def _status_client():
    """状态探测专用客户端：短超时 + 少重试，避免阻塞 UI 启动。"""
    from core.github_client import GitHubClient

    return GitHubClient(timeout=5, retry=1)


@st.cache_data(ttl=3600, show_spinner=False)
def _check_github_status() -> dict:
    """缓存 3600 秒的 GitHub 登录状态检查（仅在用户主动触发时调用）。"""
    try:
        client = _status_client()
        login = client.authenticate()
        rate = client.rate_limit()
        return {"ok": True, "login": login, "source": settings.github_token_source,
                "remaining": rate.get("remaining"), "limit": rate.get("limit")}
    except Exception as exc:  # noqa: BLE001 —— 网络/证书/代理异常统一降级为「未就绪」
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# 核心 Services 缓存工厂（页面刷新不会重复实例化 / 重复网络探测）
# ---------------------------------------------------------------------------
@st.cache_resource(ttl=3600, show_spinner=False)
def get_hosting_service():
    """缓存一键托管服务实例。"""
    from services.hosting_service import HostingService

    return HostingService()


@st.cache_resource(ttl=3600, show_spinner=False)
def get_release_service():
    """缓存发版服务实例。"""
    from services.release_service import ReleaseService

    return ReleaseService()


@st.cache_resource(ttl=3600, show_spinner=False)
def get_star_search_service():
    """缓存 Star 语义搜索服务实例。"""
    from services.star_search_service import StarSearchService

    return StarSearchService()


@st.cache_resource(ttl=3600, show_spinner=False)
def get_worklog_service():
    """缓存工作日报服务实例。"""
    from services.worklog_service import WorklogService

    return WorklogService()


def render_sidebar() -> None:
    """渲染侧边栏：状态卡片 + 配置面板 + 偏好输入。"""
    # 侧边栏品牌区（与主面板品牌条呼应，但更紧凑）
    st.sidebar.markdown(
        """
        <div class="ghai-brand" style="padding:0 2px 12px 2px;">
          <div class="ghai-brand-left">
            <div class="ghai-brand-mark" style="width:38px;height:38px;font-size:16px;">❯</div>
            <div>
              <div class="ghai-brand-title" style="font-size:16px;">GitHub-AI-Studio</div>
              <div class="ghai-brand-sub" style="font-size:10.5px;">ghai --studio</div>
            </div>
          </div>
        </div>
        <div class="ghai-hairline" style="margin-bottom:14px;"></div>
        """,
        unsafe_allow_html=True,
    )

    # ---- 语言切换（实时切换 + 持久化到 data/config.json） ----
    lang_options = {"中文": "zh_CN", "English": "en_US"}
    current_lang = st.session_state.get("lang") or app_config.get_language()
    current_label = "中文" if current_lang == "zh_CN" else "English"
    selected_label = st.sidebar.selectbox(
        "Language / 语言",
        list(lang_options),
        index=list(lang_options).index(current_label),
        key="cfg_lang",
    )
    new_lang = lang_options[selected_label]
    if new_lang != current_lang:
        st.session_state["lang"] = new_lang
        app_config.set_language(new_lang)
        st.rerun()

    # ---- GitHub 状态卡片 ----
    # 非阻塞策略：启动/刷新时不做网络探测，仅渲染上次结果或占位卡；
    # 用户点击「检测连接」后才发起短超时（5s）网络请求。
    status = st.session_state.get("gh_status")
    if status is None:
        theme.sidebar_status_card(
            None, None, ok=False,
            error=tr("sidebar.status_pending"),
        )
    elif status["ok"]:
        theme.sidebar_status_card(status["login"], status["source"], ok=True)
        remaining = status.get("remaining")
        limit = status.get("limit")
        if isinstance(remaining, int) and isinstance(limit, int) and limit > 0:
            st.sidebar.caption(f"API 配额 · {remaining:,}/{limit:,}")
            st.sidebar.progress(max(0.0, min(remaining / limit, 1.0)))
    else:
        theme.sidebar_status_card(None, None, ok=False, error=status.get("error", "未知错误"))

    if st.sidebar.button(tr("sidebar.check_connection"), use_container_width=True, key="cfg_status_check"):
        with st.spinner("正在检测 GitHub API（短超时 5s）..."):
            st.cache_data.clear()
            status = _check_github_status()
        st.session_state["gh_status"] = status
        st.rerun()

    # ---- 配置概览（纯本地读取，不触网） ----
    with st.sidebar.expander(tr("sidebar.config_overview"), expanded=False):
        configured = tr("common.configured")
        not_configured = tr("common.not_configured")
        gh_src = settings.github_token_source
        gh_label = {
            "env": "Token（.env）",
            "gh-cli": "gh CLI",
            "gh-hosts": "gh hosts.yml",
            "none": not_configured,
        }.get(gh_src, gh_src)
        theme.status_badge(
            tr("sidebar.badge_github").format(value=gh_label),
            "ok" if gh_src != "none" else "warn",
        )
        st.sidebar.write("")
        theme.status_badge(
            tr("sidebar.badge_openai").format(
                value=configured if settings.openai_api_key else not_configured
            ),
            "ok" if settings.openai_api_key else "warn",
        )
        st.sidebar.write("")
        theme.status_badge(
            tr("sidebar.badge_ntfy").format(
                value=configured if settings.ntfy_topic else not_configured
            ),
            "ok" if settings.ntfy_topic else "warn",
        )
        st.sidebar.write("")
        theme.status_badge(
            tr("sidebar.badge_notion").format(value=(
                configured if settings.notion_token and settings.notion_database_id else not_configured
            )),
            "ok" if settings.notion_token and settings.notion_database_id else "warn",
        )
        st.sidebar.write("")
        theme.status_badge(
            tr("sidebar.badge_feishu").format(
                value=configured if settings.feishu_webhook else not_configured
            ),
            "ok" if settings.feishu_webhook else "warn",
        )

    # ---- 每日自动推送（界面实时修改，后台调度器动态重排） ----
    with st.sidebar.expander(tr("sidebar.auto_push"), expanded=False):
        push_enabled = st.sidebar.toggle(
            tr("sidebar.push_enabled"),
            value=settings.auto_push_enabled,
            key="cfg_push_enabled",
        )
        try:
            push_hh, push_mm = (int(x) for x in settings.auto_push_time.split(":"))
            default_push_time = datetime.time(push_hh, push_mm)
        except (ValueError, TypeError):
            default_push_time = datetime.time(8, 30)
        push_time = st.sidebar.time_input(
            tr("sidebar.push_time"),
            value=default_push_time,
            key="cfg_push_time",
        )
        st.sidebar.caption(tr("sidebar.push_hint"))
        if st.sidebar.button(tr("sidebar.apply_push"), use_container_width=True, key="cfg_push_apply"):
            time_str = push_time.strftime("%H:%M")
            update_env_file({
                "AUTO_PUSH_ENABLED": "true" if push_enabled else "false",
                "AUTO_PUSH_TIME": time_str,
            })
            app_config.set_push_plan(push_enabled, time_str)
            from core.scheduler import DailyPushScheduler

            ok, message = DailyPushScheduler.update_schedule(push_enabled, time_str)
            st.toast(
                tr("push.updated").format(time=time_str) if ok and push_enabled
                else tr("push.disabled")
            )
            if ok:
                st.sidebar.success(
                    tr("push.updated").format(time=time_str) if push_enabled else tr("push.disabled")
                )
            else:
                st.sidebar.error(message)
            st.cache_data.clear()
            st.rerun()
        try:
            from core.scheduler import DailyPushScheduler

            next_run = DailyPushScheduler.next_run()
            if next_run:
                st.sidebar.caption(tr("sidebar.next_run").format(time=next_run.replace("T", " ")[:16]))
        except Exception:  # noqa: BLE001
            pass

    # ---- 完整配置入口（表单已移至 ⚙️ 设置 Tab） ----
    st.sidebar.caption("系统设置")
    st.sidebar.info(tr("sidebar.full_settings"))

    # ---- 个人技术偏好（多选 + 自定义标签） ----
    st.sidebar.caption(tr("sidebar.prefs_title"))
    current_stack = app_config.get_tech_stack()
    selected_tags = st.sidebar.multiselect(
        tr("sidebar.tech_stack"),
        options=app_config.DEFAULT_TECH_STACK,
        default=[t for t in current_stack if t in app_config.DEFAULT_TECH_STACK],
        key="cfg_tech_tags",
        help=tr("sidebar.interests_hint"),
    )
    custom_tags = st.sidebar.text_input(
        tr("sidebar.tech_custom"),
        value=", ".join(t for t in current_stack if t not in app_config.DEFAULT_TECH_STACK),
        key="cfg_tech_custom",
    )
    theme.chips(current_stack, fallback=tr("common.not_configured"))
    if st.sidebar.button(tr("common.save_prefs"), use_container_width=True, key="cfg_interests_save"):
        tags = selected_tags + [x.strip() for x in custom_tags.split(",") if x.strip()]
        app_config.set_tech_stack(tags)
        update_env_file({"USER_INTERESTS": ", ".join(tags)})
        st.sidebar.success(tr("sidebar.tech_saved"))
        st.cache_data.clear()
        st.rerun()

    st.sidebar.divider()
    st.sidebar.caption(tr("sidebar.footer_hint"))


def get_github_client():
    """获取可用 GitHub 客户端；未配置凭证时在 UI 中停止并提示。"""
    try:
        return _cached_client()
    except Exception as exc:  # noqa: BLE001 —— UI 边界统一提示
        st.error(f"❌ {exc}")
        st.stop()


def render_error(exc: Exception) -> None:
    """统一错误渲染（st.error + 展开详情）。"""
    st.error(f"❌ 操作失败：{exc}")
    if hasattr(exc, "__cause__") and exc.__cause__:
        with st.expander("查看底层错误"):
            st.code(str(exc.__cause__))
