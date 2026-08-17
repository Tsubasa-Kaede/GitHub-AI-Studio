# -*- coding: utf-8 -*-
"""
GitHub-AI-Studio 独立界面控制台（Tkinter 桌面窗口）
====================================================

这是一个真正的桌面 GUI 应用窗口（不依赖浏览器、不依赖终端）：
    - 左侧功能导航 / 顶部 7 大标签页；
    - 所有长耗时操作在后台线程执行，界面不卡顿；
    - Token / API Key 输入框全部密码遮罩；
    - 复用 services / core 业务层，架构与 TUI / CLI 完全一致。

运行：
    python gui_app.py            # 开发调试
    打包后：GitHub-AI-Studio.exe（--windowed，双击即开，无控制台窗口）
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk
from typing import Callable, List, Optional

import config
from core.ai_engine import AIEngine
from core.git_engine import commit, get_diff, get_repo, has_remote, push, stage_all
from core.notion_engine import NotionArchiver
from core.ntfy_engine import NtfyEngine
from core.security_guard import SecurityGuard
from services.hosting_service import HostingService
from services.release_service import ReleaseService
from services.star_search_service import StarSearchService
from services.trending_service import run_daily_trending_pipeline
from services.worklog_service import WorklogService

# ---------------------------------------------------------------------------
# 深色主题配色
# ---------------------------------------------------------------------------
BG = "#0E1117"
PANEL = "#161A26"
ACCENT = "#7C5CFF"
TEXT = "#F0F2F5"
MUTED = "#8B93A7"
GREEN = "#3FB950"
RED = "#F85149"
YELLOW = "#D29922"
FONT = ("Microsoft YaHei UI", 10)
FONT_BOLD = ("Microsoft YaHei UI", 10, "bold")


class GitHubAIStudioApp(tk.Tk):
    """独立桌面控制台主窗口。"""

    def __init__(self) -> None:
        super().__init__()
        self.title("GitHub-AI-Studio 控制台")
        self.geometry("1120x760")
        self.minsize(960, 640)
        self.configure(bg=BG)

        # 后台线程 → 主线程的消息队列
        self._queue: queue.Queue = queue.Queue()
        self._trending_items: List = []

        self._setup_style()
        self._build_layout()
        self._build_hosting_tab()
        self._build_commit_tab()
        self._build_trending_tab()
        self._build_release_tab()
        self._build_star_tab()
        self._build_worklog_tab()
        self._build_settings_tab()

        self.after(80, self._poll_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # 样式与布局
    # ------------------------------------------------------------------
    def _setup_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", background=BG, foreground=TEXT, font=FONT)
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=PANEL, foreground=TEXT, padding=(16, 8), font=FONT_BOLD)
        style.map("TNotebook.Tab", background=[("selected", ACCENT)], foreground=[("selected", "#FFFFFF")])
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=TEXT)
        style.configure("Card.TLabel", background=PANEL, foreground=TEXT)
        style.configure("Muted.TLabel", background=BG, foreground=MUTED)
        style.configure("TEntry", fieldbackground="#0D1117", foreground=TEXT, insertcolor=TEXT, bordercolor=PANEL)
        style.configure("TCombobox", fieldbackground="#0D1117", foreground=TEXT, background=PANEL)
        style.configure("TButton", background=PANEL, foreground=TEXT, padding=(10, 5), borderwidth=0)
        style.map("TButton", background=[("active", "#2A3040"), ("pressed", ACCENT)])
        style.configure("Accent.TButton", background=ACCENT, foreground="#FFFFFF", font=FONT_BOLD)
        style.map("Accent.TButton", background=[("active", "#9A86FF")])
        style.configure("TProgressbar", background=ACCENT, troughcolor=PANEL, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(18, 9))

    def _build_layout(self) -> None:
        """顶部标题 + 状态栏 + 主标签页。"""
        header = tk.Frame(self, bg=PANEL)
        header.pack(fill="x")
        tk.Label(header, text="GitHub-AI-Studio", bg=PANEL, fg=ACCENT,
                 font=("Microsoft YaHei UI", 16, "bold")).pack(side="left", padx=16, pady=10)
        tk.Label(header, text="独立桌面控制台 · 本地 GitHub 智能化管理",
                 bg=PANEL, fg=MUTED).pack(side="left", padx=4)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.status_var = tk.StringVar(value="就绪")
        tk.Label(self, textvariable=self.status_var, bg=BG, fg=MUTED,
                 anchor="w", font=("Microsoft YaHei UI", 9)).pack(fill="x", padx=12, pady=(0, 6))

    # ------------------------------------------------------------------
    # 通用工具
    # ------------------------------------------------------------------
    def _add_tab(self, title: str) -> ttk.Frame:
        """创建带 padding 的标签页容器。"""
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text=title)
        return frame

    def _entry_row(self, parent, label: str, *, password: bool = False, width: int = 64):
        """创建「标签 + 输入框」一行，返回 (StringVar, Entry)。"""
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text=label, width=18, style="Muted.TLabel").pack(side="left")
        var = tk.StringVar()
        entry = ttk.Entry(row, textvariable=var, width=width, show="*" if password else "")
        entry.pack(side="left", fill="x", expand=True)
        return var, entry

    def _log_box(self, parent, height: int = 8):
        """创建带配色标签的日志文本框。"""
        box = scrolledtext.ScrolledText(
            parent, height=height, bg="#0D1117", fg=TEXT, insertbackground=TEXT,
            relief="flat", borderwidth=0, font=("Consolas", 10),
            state="disabled", wrap="word",
        )
        box.pack(fill="both", expand=True, pady=(6, 0))
        box.tag_configure("ok", foreground=GREEN)
        box.tag_configure("err", foreground=RED)
        box.tag_configure("warn", foreground=YELLOW)
        box.tag_configure("info", foreground=TEXT)
        box.tag_configure("muted", foreground=MUTED)
        box.tag_configure("head", foreground=ACCENT, font=("Consolas", 11, "bold"))
        return box

    @staticmethod
    def log(box, text: str, tag: str = "info") -> None:
        """向日志框追加一行（线程安全：仅主线程调用）。"""
        box.configure(state="normal")
        box.insert("end", text + "\n", tag)
        box.configure(state="disabled")
        box.see("end")

    def _async(self, work: Callable, done: Optional[Callable] = None) -> None:
        """后台线程执行 work；完成后把 done 回调投递回主线程。"""

        def worker() -> None:
            try:
                result = work()
                if done:
                    self._queue.put(lambda: done(result, None))
            except Exception as exc:  # noqa: BLE001
                if done:
                    self._queue.put(lambda: done(None, exc))

        threading.Thread(target=worker, daemon=True).start()

    def _poll_queue(self) -> None:
        """主线程轮询消息队列，执行 UI 更新回调。"""
        try:
            while True:
                callback = self._queue.get_nowait()
                callback()
        except queue.Empty:
            pass
        self.after(80, self._poll_queue)

    def _progress_cb(self, progressbar, status_var, pct: int, message: str) -> None:
        """后台线程进度回调 → 投递到主线程更新。"""

        def update() -> None:
            progressbar["value"] = pct
            status_var.set(f"[{pct}%] {message}")

        self._queue.put(update)

    def _on_close(self) -> None:
        """关闭窗口（后台 daemon 线程随进程退出）。"""
        self.destroy()

    # ==================================================================
    # Tab 1：一键托管
    # ==================================================================
    def _build_hosting_tab(self) -> None:
        tab = self._add_tab("🚀 一键托管")
        ttk.Label(tab, text="本地目录 → AI 多语言 README → 创建 GitHub 仓库 → 自动提交推送",
                  style="Muted.TLabel").pack(anchor="w")

        self.host_path, _ = self._entry_row(tab, "项目路径", width=70)
        self.host_path.set("C:\\Users\\夜缘\\Documents\\Codex")
        self.host_name, _ = self._entry_row(tab, "仓库名（留空取目录名）")
        self.host_langs, _ = self._entry_row(tab, "README 语言", width=30)
        self.host_langs.set("zh-CN,en")
        vis_row = ttk.Frame(tab)
        vis_row.pack(fill="x", pady=4)
        ttk.Label(vis_row, text="仓库可见性", width=18, style="Muted.TLabel").pack(side="left")
        self.host_vis = ttk.Combobox(vis_row, values=["private", "public"], state="readonly", width=10)
        self.host_vis.set("private")
        self.host_vis.pack(side="left")

        self.host_progress = ttk.Progressbar(tab, maximum=100)
        self.host_progress.pack(fill="x", pady=(8, 2))
        ttk.Button(tab, text="开始一键托管", style="Accent.TButton",
                   command=self._do_hosting).pack(anchor="w", pady=4)
        self.host_log = self._log_box(tab, height=10)

    def _do_hosting(self) -> None:
        path = self.host_path.get().strip()
        if not path:
            messagebox.showwarning("提示", "请填写项目路径")
            return

        def work():
            from pathlib import Path
            name = self.host_name.get().strip() or Path(path).name
            langs = [x.strip() for x in self.host_langs.get().split(",") if x.strip()] or ["zh-CN", "en"]
            return HostingService().run(
                path=path, repo_name=name, visibility=self.host_vis.get(),
                readme_languages=langs,
                progress_cb=lambda p, m: self._progress_cb(self.host_progress, self.status_var, p, m),
            )

        def done(result, err):
            if err:
                self.log(self.host_log, f"❌ 托管失败：{err}", "err")
                self.status_var.set("托管失败")
                return
            files = ", ".join(result.readme_files) if result.readme_files else "保留原文件"
            self.log(self.host_log, f"🎉 托管成功：{result.repo_url}", "ok")
            self.log(self.host_log, f"   提交 {result.commit_sha} · README：{files}", "muted")
            self.status_var.set("托管成功")

        self.log(self.host_log, "开始托管...", "info")
        self._async(work, done)

    # ==================================================================
    # Tab 2：AI Commit
    # ==================================================================
    def _build_commit_tab(self) -> None:
        tab = self._add_tab("📝 AI Commit")
        self.commit_path, _ = self._entry_row(tab, "Git 仓库路径")

        btns = ttk.Frame(tab)
        btns.pack(fill="x", pady=4)
        ttk.Button(btns, text="读取 Diff", command=self._commit_diff).pack(side="left", padx=2)
        ttk.Button(btns, text="安全扫描", command=self._commit_scan).pack(side="left", padx=2)
        ttk.Button(btns, text="AI 生成提交信息", command=self._commit_ai).pack(side="left", padx=2)
        ttk.Button(btns, text="提交并推送", style="Accent.TButton",
                   command=self._commit_push).pack(side="left", padx=2)

        self.commit_message = scrolledtext.ScrolledText(
            tab, height=5, bg="#0D1117", fg=TEXT, insertbackground=TEXT,
            relief="flat", font=("Consolas", 10),
        )
        self.commit_message.pack(fill="x", pady=6)
        self.commit_log = self._log_box(tab, height=8)

    def _commit_diff(self) -> None:
        path = self.commit_path.get().strip()

        def work():
            diff = get_diff(get_repo(path))
            return diff

        def done(diff, err):
            if err:
                self.log(self.commit_log, f"❌ {err}", "err")
                return
            self.log(self.commit_log, f"变更文件：{diff.file_count}", "head")
            self.log(self.commit_log, diff.diff_stat or "(无统计)", "muted")
            self.log(self.commit_log, diff.diff_text[:2500] or "工作区干净", "info")
            self.commit_message.delete("1.0", "end")

        self._async(work, done)

    def _commit_scan(self) -> None:
        path = self.commit_path.get().strip()

        def work():
            return SecurityGuard().scan_path(path)

        def done(hits, err):
            if err:
                self.log(self.commit_log, f"❌ {err}", "err")
                return
            if hits:
                self.log(self.commit_log, f"⛔ 发现 {len(hits)} 处敏感信息：", "err")
                for h in hits[:10]:
                    self.log(self.commit_log, f"   {h['file']}:{h['line']} [{h['pattern']}]", "err")
            else:
                self.log(self.commit_log, "✅ 未发现硬编码密钥。", "ok")

        self._async(work, done)

    def _commit_ai(self) -> None:
        path = self.commit_path.get().strip()

        def work():
            diff = get_diff(get_repo(path))
            if not diff.has_changes:
                raise RuntimeError("工作区干净，没有需要提交的变更")
            return AIEngine().generate_commit_message(diff.diff_text, diff.diff_stat)

        def done(message, err):
            if err:
                self.log(self.commit_log, f"❌ {err}", "err")
                return
            self.commit_message.delete("1.0", "end")
            self.commit_message.insert("1.0", message)
            self.log(self.commit_log, "✅ AI 提交信息已生成，可编辑后提交。", "ok")

        self._async(work, done)

    def _commit_push(self) -> None:
        path = self.commit_path.get().strip()
        message = self.commit_message.get("1.0", "end").strip()

        def work():
            if not message:
                raise RuntimeError("提交信息不能为空")
            repo = get_repo(path)
            hits = SecurityGuard().scan_text(get_diff(repo).diff_text)
            if hits:
                raise RuntimeError(f"敏感信息拦截：{hits[0]['pattern']}（第 {hits[0]['line']} 行）")
            if not has_remote(repo):
                raise RuntimeError("未配置 origin 远程，请先在一键托管中建仓")
            stage_all(repo)
            short = commit(repo, message)
            push(repo, "origin")
            return short

        def done(short, err):
            if err:
                self.log(self.commit_log, f"❌ {err}", "err")
                return
            self.log(self.commit_log, f"✅ 已提交 {short} 并推送：{message.splitlines()[0]}", "ok")

        self._async(work, done)

    # ==================================================================
    # Tab 3：中文热榜
    # ==================================================================
    def _build_trending_tab(self) -> None:
        tab = self._add_tab("🔥 中文热榜")
        btns = ttk.Frame(tab)
        btns.pack(fill="x", pady=4)
        ttk.Button(btns, text="抓取并 AI 翻译", style="Accent.TButton",
                   command=self._trending_fetch).pack(side="left", padx=2)
        ttk.Button(btns, text="推送到 Ntfy", command=self._trending_push).pack(side="left", padx=2)
        ttk.Button(btns, text="归档 Notion", command=self._trending_archive).pack(side="left", padx=2)
        self.trending_progress = ttk.Progressbar(tab, maximum=100)
        self.trending_progress.pack(fill="x", pady=(4, 2))
        self.trending_log = self._log_box(tab, height=14)
        self.trending_log.tag_configure("card", foreground=TEXT, font=("Consolas", 10, "bold"))

    def _trending_fetch(self) -> None:
        self.log(self.trending_log, "抓取中...", "muted")

        def work():
            return run_daily_trending_pipeline(
                do_push=False, do_archive=False,
                progress_cb=lambda p, m: self._progress_cb(self.trending_progress, self.status_var, p, m),
            )

        def done(result, err):
            if err:
                self.log(self.trending_log, f"❌ {err}", "err")
                return
            if not result.success:
                self.log(self.trending_log, f"❌ {result.error}", "err")
                return
            self._trending_items = result.items
            self.log(self.trending_log, f"共 {len(result.items)} 条推荐：\n", "head")
            for i, repo in enumerate(result.items, start=1):
                score = f"{repo.match_score:.1f}/10" if repo.match_score else "-"
                self.log(self.trending_log, f"{i}. {repo.name}  🔥 {score}", "card")
                if repo.zh_position:
                    self.log(self.trending_log, f"   定位：{repo.zh_position}", "info")
                self.log(self.trending_log, f"   摘要：{repo.zh_summary or repo.description}", "info")
                tags = " ".join(f"#{t}" for t in repo.tags) or "#多语言"
                stars = f"{repo.stars_total / 1000:.1f}k" if repo.stars_total >= 1000 else str(repo.stars_total)
                self.log(self.trending_log, f"   ⭐ {stars} Stars · {repo.language or '多语言'} · {tags}", "muted")
            self.status_var.set("热榜抓取完成")

        self._async(work, done)

    def _trending_push(self) -> None:
        def work():
            return NtfyEngine().send_trending(self._trending_items)

        def done(result, err):
            if err:
                self.log(self.trending_log, f"❌ {err}", "err")
                return
            self.log(self.trending_log, f"📱 Ntfy 推送结果：{result}", "ok")

        if not self._trending_items:
            self.log(self.trending_log, "请先抓取热榜。", "warn")
            return
        self._async(work, done)

    def _trending_archive(self) -> None:
        def work():
            return NotionArchiver().archive_many(self._trending_items)

        def done(urls, err):
            if err:
                self.log(self.trending_log, f"❌ {err}", "err")
                return
            self.log(self.trending_log, f"📚 已归档 {len(urls)} 条：{', '.join(urls.values())}", "ok")

        if not self._trending_items:
            self.log(self.trending_log, "请先抓取热榜。", "warn")
            return
        self._async(work, done)

    # ==================================================================
    # Tab 4：自动发版
    # ==================================================================
    def _build_release_tab(self) -> None:
        tab = self._add_tab("📦 自动发版")
        self.release_path, _ = self._entry_row(tab, "Git 仓库路径")
        self.release_tag, _ = self._entry_row(tab, "版本 Tag")
        self.release_repo, _ = self._entry_row(tab, "GitHub 仓库全名")
        btns = ttk.Frame(tab)
        btns.pack(fill="x", pady=4)
        ttk.Button(btns, text="生成 CHANGELOG", style="Accent.TButton",
                   command=self._release_generate).pack(side="left", padx=2)
        ttk.Button(btns, text="发布 Release", command=self._release_publish).pack(side="left", padx=2)
        self.release_text = scrolledtext.ScrolledText(
            tab, height=10, bg="#0D1117", fg=TEXT, insertbackground=TEXT,
            relief="flat", font=("Consolas", 10),
        )
        self.release_text.pack(fill="both", expand=True, pady=6)

    def _release_generate(self) -> None:
        path, tag = self.release_path.get().strip(), self.release_tag.get().strip()

        def work():
            if not path or not tag:
                raise RuntimeError("请填写仓库路径与 Tag")
            return ReleaseService().generate(path, tag)

        def done(info, err):
            if err:
                messagebox.showerror("生成失败", str(err))
                return
            self._release_info = info
            self.release_text.delete("1.0", "end")
            self.release_text.insert("1.0", info.changelog)
            self.status_var.set(f"已基于 {info.commits_count} 条提交生成 CHANGELOG")

        self._async(work, done)

    def _release_publish(self) -> None:
        def work():
            info = getattr(self, "_release_info", None)
            if info is None:
                raise RuntimeError("请先生成 CHANGELOG")
            if not self.release_repo.get().strip():
                raise RuntimeError("请填写 GitHub 仓库全名")
            return ReleaseService().publish(
                self.release_repo.get().strip(), info,
                body=self.release_text.get("1.0", "end").strip(),
            )

        def done(result, err):
            if err:
                messagebox.showerror("发布失败", str(err))
                return
            messagebox.showinfo("发布成功", f"Release 已发布：\n{result['url']}")

        self._async(work, done)

    # ==================================================================
    # Tab 5：Star 语义搜索
    # ==================================================================
    def _build_star_tab(self) -> None:
        tab = self._add_tab("🔍 Star 搜索")
        self.star_query, _ = self._entry_row(tab, "搜索需求")
        self.star_query.set("好用的 Python 截图库")
        ttk.Button(tab, text="语义搜索", style="Accent.TButton",
                   command=self._star_search).pack(anchor="w", pady=4)
        self.star_log = self._log_box(tab, height=12)

    def _star_search(self) -> None:
        query = self.star_query.get().strip()

        def work():
            if not query:
                raise RuntimeError("请输入搜索需求")
            return StarSearchService().search(query)

        def done(results, err):
            if err:
                self.log(self.star_log, f"❌ {err}", "err")
                return
            self.log(self.star_log, f"找到 {len(results)} 个匹配仓库：\n", "head")
            for item in results:
                repo = item["repo"]
                self.log(self.star_log, f"{repo.full_name}  🔥 {item['score']:.1f}/10", "card")
                self.log(self.star_log, f"   ⭐ {repo.stars} · {repo.language or '多语言'} · {repo.html_url}", "muted")
                if repo.description:
                    self.log(self.star_log, f"   {repo.description[:120]}", "info")
                self.log(self.star_log, f"   💡 {item['reason']}", "muted")

        self._async(work, done)

    # ==================================================================
    # Tab 6：工作日报
    # ==================================================================
    def _build_worklog_tab(self) -> None:
        tab = self._add_tab("📋 工作日报")
        self.worklog_path, _ = self._entry_row(tab, "Git 仓库路径")
        period_row = ttk.Frame(tab)
        period_row.pack(fill="x", pady=4)
        ttk.Label(period_row, text="统计周期", width=18, style="Muted.TLabel").pack(side="left")
        self.worklog_period = ttk.Combobox(period_row, values=["today", "week"], state="readonly", width=10)
        self.worklog_period.set("today")
        self.worklog_period.pack(side="left")
        btns = ttk.Frame(tab)
        btns.pack(fill="x", pady=4)
        ttk.Button(btns, text="生成日报", style="Accent.TButton",
                   command=self._worklog_generate).pack(side="left", padx=2)
        ttk.Button(btns, text="复制到剪贴板", command=self._worklog_copy).pack(side="left", padx=2)
        self.worklog_text = scrolledtext.ScrolledText(
            tab, height=14, bg="#0D1117", fg=TEXT, insertbackground=TEXT,
            relief="flat", font=("Consolas", 10),
        )
        self.worklog_text.pack(fill="both", expand=True, pady=6)

    def _worklog_generate(self) -> None:
        path = self.worklog_path.get().strip()

        def work():
            if not path:
                raise RuntimeError("请填写 Git 仓库路径")
            return WorklogService().generate(path, self.worklog_period.get())

        def done(result, err):
            if err:
                messagebox.showerror("生成失败", str(err))
                return
            self.worklog_text.delete("1.0", "end")
            self.worklog_text.insert("1.0", result.markdown)
            self.status_var.set(f"已基于 {result.commits_count} 条提交生成日报")

        self._async(work, done)

    def _worklog_copy(self) -> None:
        text = self.worklog_text.get("1.0", "end").strip()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.status_var.set("已复制到剪贴板")

    # ==================================================================
    # Tab 7：设置
    # ==================================================================
    def _build_settings_tab(self) -> None:
        tab = self._add_tab("⚙️ 设置")
        ttk.Label(tab, text="敏感字段已启用密码遮罩；保存后写入 .env 并立即生效。",
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 6))
        self.set_github, _ = self._entry_row(tab, "GITHUB_TOKEN", password=True)
        self.set_openai, _ = self._entry_row(tab, "OPENAI_API_KEY", password=True)
        self.set_ntfy_topic, _ = self._entry_row(tab, "NTFY_TOPIC")
        self.set_ntfy_server, _ = self._entry_row(tab, "NTFY_SERVER")
        self.set_ntfy_token, _ = self._entry_row(tab, "NTFY_TOKEN", password=True)
        self.set_notion_token, _ = self._entry_row(tab, "NOTION_TOKEN", password=True)
        self.set_notion_db, _ = self._entry_row(tab, "NOTION_DATABASE_ID")
        self.set_interests, _ = self._entry_row(tab, "USER_INTERESTS")
        self.set_github.set(config.settings.github_token)
        self.set_openai.set(config.settings.openai_api_key)
        self.set_ntfy_topic.set(config.settings.ntfy_topic)
        self.set_ntfy_server.set(config.settings.ntfy_server)
        self.set_ntfy_token.set(config.settings.ntfy_token)
        self.set_notion_token.set(config.settings.notion_token)
        self.set_notion_db.set(config.settings.notion_database_id)
        self.set_interests.set(", ".join(config.settings.user_interests))
        ttk.Button(tab, text="保存配置", style="Accent.TButton",
                   command=self._settings_save).pack(anchor="w", pady=8)

    def _settings_save(self) -> None:
        try:
            changed = config.update_env_file({
                "GITHUB_TOKEN": self.set_github.get(),
                "OPENAI_API_KEY": self.set_openai.get(),
                "NTFY_TOPIC": self.set_ntfy_topic.get(),
                "NTFY_SERVER": self.set_ntfy_server.get(),
                "NTFY_TOKEN": self.set_ntfy_token.get(),
                "NOTION_TOKEN": self.set_notion_token.get(),
                "NOTION_DATABASE_ID": self.set_notion_db.get(),
                "USER_INTERESTS": self.set_interests.get(),
            })
            messagebox.showinfo("保存成功", f"已保存：{', '.join(changed) if changed else '无变更'}")
            self.status_var.set("配置已保存并生效")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("保存失败", str(exc))


def main() -> None:
    """启动桌面控制台。"""
    app = GitHubAIStudioApp()
    app.mainloop()


if __name__ == "__main__":
    main()
