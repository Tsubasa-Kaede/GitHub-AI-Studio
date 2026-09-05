# -*- coding: utf-8 -*-
"""Tab 2：📝 AI 智能 Commit & 安全扫描（含依赖漏洞扫描）。"""

from __future__ import annotations

import streamlit as st

from ui.components import render_error, tr
from ui import theme


def render() -> None:
    """渲染 AI Commit 页面。"""
    theme.section_header("", tr("commit.title"), tr("commit.desc"))
    theme.tagline(["读取 Diff", "密钥扫描", "依赖漏洞", "AI 生成", "一键推送"])

    with st.container(border=True):
        path = st.text_input(
            "本地 Git 仓库目录", placeholder="C:\\Users\\you\\my-project", key="commit_path"
        )
        row1_c1, row1_c2 = st.columns(2)
        with row1_c1:
            if st.button(tr("commit.load_diff"), use_container_width=True, disabled=not path, key="commit_load_diff"):
                try:
                    from core.git_engine import get_diff, get_repo

                    repo = get_repo(path)
                    diff = get_diff(repo)
                    st.session_state["commit_diff"] = diff
                    st.session_state["commit_repo_path"] = path
                except Exception as exc:  # noqa: BLE001
                    render_error(exc)
        with row1_c2:
            if st.button(tr("commit.scan_keys"), use_container_width=True, disabled=not path, key="commit_scan_keys"):
                try:
                    from core.security_guard import SecurityGuard

                    hits = SecurityGuard().scan_path(path)
                    if hits:
                        st.error(f"发现 {len(hits)} 处疑似敏感信息：")
                        for hit in hits[:8]:
                            st.code(f"[{hit['pattern']}] {hit['file']}:{hit['line']} {hit['snippet']}")
                    else:
                        st.success("✓ 未发现硬编码密钥。")
                except Exception as exc:  # noqa: BLE001
                    render_error(exc)
        row2_c1, row2_c2 = st.columns(2)
        with row2_c1:
            if st.button(tr("commit.scan_deps"), use_container_width=True, disabled=not path, key="commit_scan_deps"):
                try:
                    from core.security_guard import SecurityGuard

                    with st.spinner("查询 OSV 漏洞库..."):
                        findings = SecurityGuard().scan_dependencies(path)
                    if findings:
                        st.error(f"发现 {len(findings)} 个存在已知漏洞的依赖：")
                        for f in findings:
                            vulns = "；".join(v["id"] for v in f["vulns"])
                            st.code(f"{f['package']}=={f['version']} [{f['ecosystem']}] → {vulns}")
                    else:
                        st.success("✓ 未发现已知漏洞（或无锁定版本的依赖清单）。")
                except Exception as exc:  # noqa: BLE001
                    render_error(exc)
        with row2_c2:
            if st.button(
                tr("commit.gen_message"), use_container_width=True,
                disabled="commit_diff" not in st.session_state, key="commit_ai_generate"
            ):
                try:
                    from core.ai_engine import AIEngine, AIEngineError

                    diff = st.session_state["commit_diff"]
                    try:
                        message = AIEngine().generate_commit_message(diff.diff_text, diff.diff_stat)
                    except AIEngineError as exc:
                        st.warning(f"{exc}（将使用本地规则）")
                        message = AIEngine().generate_commit_message(diff.diff_text)
                    st.session_state["commit_message_editor"] = message
                except Exception as exc:  # noqa: BLE001
                    render_error(exc)

    diff = st.session_state.get("commit_diff")
    hits: list = []
    if diff is not None:
        with st.container(border=True):
            if not diff.has_changes:
                st.success("✓ 工作区干净，没有需要提交的变更。")
            else:
                col_m1, col_m2 = st.columns(2)
                col_m1.metric("变更文件数", diff.file_count)
                col_m2.metric("状态", "有未提交变更")
                with st.expander("查看 Diff 统计", expanded=False):
                    st.code(diff.diff_stat or "(无统计)")
                with st.expander("查看 Diff 预览（截断）", expanded=False):
                    st.code(diff.diff_text[:4000])

            # 敏感信息拦截（提交前自动执行）
            from core.security_guard import SecurityGuard

            hits = SecurityGuard().scan_text(diff.diff_text)
            if hits:
                st.error(f"检测到 {len(hits)} 处疑似敏感信息，已阻断提交！")
                for hit in hits[:5]:
                    st.code(f"[{hit['pattern']}] 第 {hit['line']} 行：{hit['snippet']}")

    with st.container(border=True):
        message = st.text_area(
            "提交信息（可编辑）",
            value=st.session_state.get("commit_message_editor", ""),
            height=120,
            key="commit_message_editor",
            disabled="commit_diff" not in st.session_state,
        )
        if st.button(tr("commit.push"), type="primary", use_container_width=True,
                     disabled=not (message.strip() and "commit_diff" in st.session_state) or bool(hits),
                     key="commit_push"):
            try:
                from core.env_guard import unignored_env_files
                from core.git_engine import commit, get_repo, has_remote, push, stage_all

                repo = get_repo(st.session_state["commit_repo_path"])
                if hits:
                    st.error("检测到敏感信息，已拦截提交。请先移除后重试。")
                    return
                leaked = unignored_env_files(repo)
                if leaked:
                    st.error(
                        "工作区存在未忽略的环境变量文件，已拦截提交："
                        + ", ".join(leaked)
                        + "。请删除或加入 .gitignore 后重试。"
                    )
                    return
                stage_all(repo)
                short = commit(repo, message)
                if not has_remote(repo):
                    st.error("当前仓库没有 origin 远程，请先在「一键托管」建仓或手动 git remote add origin。")
                    return
                push(repo, "origin")
                st.success(f"✓ 已提交 {short} 并推送：{message.splitlines()[0]}")
                st.session_state.pop("commit_diff", None)
                st.session_state.pop("commit_message_editor", None)
            except Exception as exc:  # noqa: BLE001
                render_error(exc)
