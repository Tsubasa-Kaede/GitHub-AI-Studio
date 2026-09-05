# -*- coding: utf-8 -*-
"""Tab 7：⚙️ 极简配置中心（表单 + 一键连通测试 + 热重载）。"""

from __future__ import annotations

import time

import streamlit as st

import config
from config import settings, update_env_file
from ui import theme
from ui.components import tr


def _fmt_ms(elapsed_ms: int) -> str:
    """把毫秒格式化为 XXms 或 X.Xs。"""
    return f"{elapsed_ms}ms" if elapsed_ms < 1000 else f"{elapsed_ms / 1000:.1f}s"


def _show_result(result: dict, ok_text: str) -> None:
    """统一渲染测试结果：绿标成功 / 红标失败 + 耗时。"""
    if result.get("ok"):
        st.success(f"✅ {ok_text}（耗时 {_fmt_ms(result.get('elapsed_ms', 0))}）")
    else:
        st.error(f"❌ {result.get('message', '连接失败')}（耗时 {_fmt_ms(result.get('elapsed_ms', 0))}）")


def _test_ai(api_key: str, base_url: str, model: str) -> dict:
    """用表单当前值测试 AI 连通性（无需先保存）。"""
    from core.ai_engine import AIEngine

    return AIEngine(api_key=api_key or None, base_url=base_url or None, model=model or None).ping()


def _test_github(token: str) -> dict:
    """测试 GitHub Token 与 API 连通性（短超时 5s）。"""
    from core.github_client import GitHubClient

    start = time.perf_counter()
    try:
        client = GitHubClient(token=token or None, timeout=5, retry=1)
        login = client.authenticate()
        rate = client.rate_limit()
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        message = f"登录成功：{login}"
        if rate.get("remaining") is not None:
            message += f" · 配额 {rate['remaining']}/{rate['limit']}"
        return {"ok": True, "message": message, "elapsed_ms": elapsed_ms}
    except Exception as exc:  # noqa: BLE001 —— UI 边界统一转为结果
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return {"ok": False, "message": str(exc), "elapsed_ms": elapsed_ms}


def _test_notion(token: str, database_id: str) -> dict:
    """用表单当前值测试 Notion 数据库访问权限。"""
    from core.notion_engine import NotionArchiver

    return NotionArchiver(token=token or None, database_id=database_id or None).test()


def _test_ntfy(server: str, topic: str, token: str) -> dict:
    """用表单当前值向手机发送一条测试通知。"""
    from core.ntfy_engine import NtfyEngine

    return NtfyEngine(server=server or None, topic=topic or None, token=token or None).test()


def _test_feishu(webhook_url: str, secret: str) -> dict:
    """用表单当前值发送一张飞书测试卡片。"""
    from core.feishu_engine import FeishuEngine

    return FeishuEngine(webhook_url=webhook_url or None, secret=secret or None).test()


def _save_all(fields: dict) -> None:
    """写入 .env 并热重载：清空全部缓存，使新配置立即生效。"""
    changed = update_env_file(fields)
    st.cache_data.clear()
    st.cache_resource.clear()
    if changed:
        st.success(f"💾 已保存并热重载：{', '.join(changed)}")
        st.toast("配置已生效，无需重启应用")
    else:
        st.info("配置无变更。")
    st.rerun()


def _source_badge() -> None:
    """展示当前 GitHub 凭证来源（env / gh-cli / gh-hosts / none）。"""
    src = settings.github_token_source
    label = {
        "env": "环境变量 / .env",
        "gh-cli": "gh auth token",
        "gh-hosts": "~/.config/gh/hosts.yml",
        "none": "未检测到凭证",
    }.get(src, src)
    tone = "ok" if src != "none" else "warn"
    theme.status_badge(f"GitHub 凭证来源：{label}", tone)
    st.write("")


def render() -> None:
    """渲染极简配置中心：四个服务卡片 + 一键测试 + 保存热重载。"""
    theme.section_header(
        "", tr("settings.title"), tr("settings.desc"),
    )
    theme.tagline(["填写配置", "一键测试", "保存生效"])

    _source_badge()

    # ---- LLM 配置 ----
    with st.container(border=True):
        st.markdown(f"#### {tr('settings.llm')}")
        col_l1, col_l2 = st.columns(2)
        with col_l1:
            ai_key = st.text_input(
                "OPENAI_API_KEY", value=settings.openai_api_key,
                type="password", key="set_ai_key",
                help="可填 OpenRouter / 硅基流动等 OpenAI 兼容服务 Key",
            )
        with col_l2:
            ai_model = st.text_input(
                "OPENAI_MODEL", value=settings.openai_model, key="set_ai_model",
                placeholder="gpt-4o-mini",
            )
        ai_base = st.text_input(
            "OPENAI_BASE_URL（可选，兼容中转）", value=settings.openai_base_url,
            key="set_ai_base", placeholder="https://api.openai.com/v1",
        )
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            commit_model = st.text_input(
                "COMMIT_MODEL（可选，覆盖提交信息模型）", value=settings.commit_model,
                key="set_commit_model", placeholder="留空用 OPENAI_MODEL",
            )
        with col_m2:
            trending_model = st.text_input(
                "TRENDING_MODEL（可选，覆盖热榜模型）", value=settings.trending_model,
                key="set_trending_model", placeholder="留空用 OPENAI_MODEL",
            )
        ai_fallback = st.text_input(
            "OPENAI_FALLBACK_MODEL（可选，备用模型降级链，逗号分隔）", value=settings.openai_fallback_model,
            key="set_ai_fallback", placeholder="gpt-4o-mini, deepseek-v3",
            help="主模型遇到限流/超时/网关错误时自动按顺序切换；留空不启用",
        )
        if st.button(tr("settings.test").format(channel="AI"), use_container_width=True, key="test_ai"):
            _show_result(_test_ai(ai_key, ai_base, ai_model), "AI 响应正常")

    # ---- GitHub 配置 ----
    with st.container(border=True):
        st.markdown(f"#### {tr('settings.github')}")
        gh_token = st.text_input(
            "GITHUB_TOKEN（可留空，自动复用 gh CLI / hosts.yml）",
            value=settings.github_token, type="password", key="set_gh_token",
        )
        if st.button(tr("settings.test").format(channel="GitHub"), use_container_width=True, key="test_github"):
            _show_result(_test_github(gh_token), "GitHub 连接正常")

    # ---- Notion 配置 ----
    with st.container(border=True):
        st.markdown(f"#### {tr('settings.notion')}")
        col_n1, col_n2 = st.columns(2)
        with col_n1:
            notion_token = st.text_input(
                "NOTION_TOKEN", value=settings.notion_token,
                type="password", key="set_notion_token",
            )
        with col_n2:
            notion_db = st.text_input(
                "NOTION_DATABASE_ID", value=settings.notion_database_id,
                key="set_notion_db", placeholder="数据库 ID（32 位）",
            )
        if st.button(tr("settings.test").format(channel="Notion"), use_container_width=True, key="test_notion"):
            _show_result(_test_notion(notion_token, notion_db), "Notion 连接正常")

    # ---- 飞书配置 ----
    with st.container(border=True):
        st.markdown(f"#### {tr('settings.feishu')}")
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            feishu_webhook = st.text_input(
                "FEISHU_WEBHOOK_URL（必填）", value=settings.feishu_webhook,
                key="set_feishu_webhook",
                placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/xxx",
            )
        with col_f2:
            feishu_secret = st.text_input(
                "FEISHU_SECRET（可选，签名校验）", value=settings.feishu_secret,
                type="password", key="set_feishu_secret",
            )
        st.caption("测试会向飞书群发送一张蓝色交互式测试卡片。")
        if st.button(tr("settings.test").format(channel="Feishu"), use_container_width=True, key="test_feishu"):
            _show_result(_test_feishu(feishu_webhook, feishu_secret), "飞书推送成功")

    # ---- NTFY 配置 ----
    with st.container(border=True):
        st.markdown(f"#### {tr('settings.ntfy')}")
        col_n1, col_n2 = st.columns(2)
        with col_n1:
            ntfy_server = st.text_input(
                "NTFY_SERVER", value=settings.ntfy_server, key="set_ntfy_server",
                placeholder="https://ntfy.sh",
            )
            ntfy_topic = st.text_input(
                "NTFY_TOPIC（订阅主题）", value=settings.ntfy_topic,
                key="set_ntfy_topic", placeholder="my-private-topic",
            )
        with col_n2:
            ntfy_token = st.text_input(
                "NTFY_TOKEN（自建服务鉴权，可选）", value=settings.ntfy_token,
                type="password", key="set_ntfy_token",
            )
            st.caption("测试会向手机发送一条真实通知。")
        if st.button(tr("settings.test").format(channel="NTFY"), use_container_width=True, key="test_ntfy"):
            _show_result(_test_ntfy(ntfy_server, ntfy_topic, ntfy_token), "NTFY 测试通知已发送")

    # ---- 保存 ----
    st.divider()
    if st.button(tr("settings.save"), type="primary",
                 use_container_width=True, key="settings_save"):
        _save_all({
            "OPENAI_API_KEY": ai_key,
            "OPENAI_MODEL": ai_model,
            "OPENAI_BASE_URL": ai_base,
            "OPENAI_FALLBACK_MODEL": ai_fallback,
            "COMMIT_MODEL": commit_model,
            "TRENDING_MODEL": trending_model,
            "GITHUB_TOKEN": gh_token,
            "NOTION_TOKEN": notion_token,
            "NOTION_DATABASE_ID": notion_db,
            "FEISHU_WEBHOOK": feishu_webhook,
            "FEISHU_SECRET": feishu_secret,
            "NTFY_SERVER": ntfy_server,
            "NTFY_TOPIC": ntfy_topic,
            "NTFY_TOKEN": ntfy_token,
        })

    st.caption(tr("settings.source_hint"))
