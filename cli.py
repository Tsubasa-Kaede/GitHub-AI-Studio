# -*- coding: utf-8 -*-
"""
GitHub-AI-Studio 无头 CLI 入口
===============================

用于定时任务与 CI，不依赖 Streamlit UI：
    python cli.py --daily-push                    # 热榜抓取 + AI 翻译 + 推送 + Notion 归档
    python cli.py --schedule-daily                # 一键配置每日 09:00 定时任务
    python cli.py --review-pr --repo owner/repo --pr-number 12
    python cli.py --check-config
"""

from __future__ import annotations

import argparse
import logging
import platform
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Sequence

import config
from config import ConfigError, LOG_DIR, validate_config
from core.ai_engine import AIEngine
from core.github_client import AI_REVIEW_MARKER, GitHubClient
from core.git_engine import GitEngineError
from services.trending_service import run_daily_trending_pipeline

VERSION = "1.0.0"


# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------
def setup_logging(verbose: bool = False, log_file: Optional[Path] = None) -> None:
    """控制台日志 + 可选文件日志（定时任务排查用）。"""
    handlers: List[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )


# ---------------------------------------------------------------------------
# 命令实现
# ---------------------------------------------------------------------------
def cmd_daily_push(args) -> int:
    """无界面执行每日热榜流水线（抓取 → AI 翻译 → 推送 → Notion 归档）。"""
    log_file = LOG_DIR / "daily_push.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logging.getLogger().addHandler(file_handler)

    print("📈 开始执行每日热榜流水线...")

    def on_progress(percent: int, message: str) -> None:
        print(f"  [{percent:>3}%] {message}")

    result = run_daily_trending_pipeline(progress_cb=on_progress)
    if not result.success:
        print(f"✖ 失败：{result.error}")
        return 1
    print(f"\n✓ 完成，共 {len(result.items)} 条推荐")
    for i, repo in enumerate(result.items, start=1):
        print(f"  {i}. {repo.name}（{repo.stars_total:,} Stars）{repo.zh_summary}")
    if result.pushed_channels:
        print(f"  手机推送：{result.pushed_channels}")
    if result.notion_page_url:
        print(f"  Notion 归档：{result.notion_page_url}")
    return 0


def cmd_schedule_daily(args) -> int:
    """一键配置每日定时任务（Windows 任务计划程序 / macOS-Linux Crontab）。"""
    time_str = args.schedule_time.strip()
    if not re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", time_str):
        raise ConfigError(f"时间格式不合法：{time_str!r}（应为 HH:MM）")
    if platform.system() == "Windows":
        return _schedule_windows(time_str)
    return _schedule_cron(time_str)


def _schedule_windows(time_str: str) -> int:
    """Windows：生成 pythonw 静默包装脚本并注册任务计划程序。"""
    project_root = config.PROJECT_ROOT
    scripts_dir = project_root / "scripts"
    scripts_dir.mkdir(exist_ok=True)
    wrapper = scripts_dir / "daily_push.cmd"
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe") if exe.with_name("pythonw.exe").exists() else exe
    cli_path = project_root / "cli.py"
    log_file = LOG_DIR / "daily_push.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    wrapper.write_text(
        f"@echo off\r\ncd /d \"{project_root}\"\r\n"
        f"\"{pythonw}\" \"{cli_path}\" --daily-push >> \"{log_file}\" 2>&1\r\n",
        encoding="utf-8",
    )
    task_name = "GitHubAIStudio_DailyPush"
    result = subprocess.run(
        ["schtasks", "/Create", "/F", "/TN", task_name, "/SC", "DAILY",
         "/ST", time_str, "/TR", f'"{wrapper}"'],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise GitEngineError(f"创建定时任务失败：{result.stderr.strip() or result.stdout.strip()}")
    print(f"✓ 已创建任务：{task_name}（每天 {time_str}）")
    print(f"  查看：schtasks /Query /TN {task_name}")
    print(f"  删除：schtasks /Delete /TN {task_name} /F")
    return 0


def _schedule_cron(time_str: str) -> int:
    """macOS / Linux：写入 crontab（自动去重旧任务）。"""
    hour, minute = time_str.split(":")
    project_root = config.PROJECT_ROOT
    log_file = LOG_DIR / "daily_push.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    line = (
        f"{minute} {hour} * * * cd \"{project_root}\" && "
        f"\"{sys.executable}\" \"{project_root / 'cli.py'}\" --daily-push >> \"{log_file}\" 2>&1"
    )
    try:
        existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        old_lines = existing.stdout.splitlines() if existing.returncode == 0 else []
    except FileNotFoundError as exc:
        raise GitEngineError("未找到 crontab 命令（macOS 自带）。") from exc
    kept = [ln for ln in old_lines if "GitHub-AI-Studio" not in ln and "cli.py --daily-push" not in ln]
    result = subprocess.run(
        ["crontab", "-"],
        input="\n".join(kept + [f"# GitHub-AI-Studio 每日热榜（{time_str}）", line]) + "\n",
        text=True, capture_output=True,
    )
    if result.returncode != 0:
        raise GitEngineError(f"写入 crontab 失败：{result.stderr.strip()}")
    print(f"✓ 已写入 crontab（每天 {time_str}）\n  {line}")
    return 0


def cmd_review_pr(args) -> int:
    """AI 审查 PR 并回复评论区（供 GitHub Actions 工作流调用）。"""
    if not args.repo or not args.pr_number:
        raise GitEngineError("--review-pr 需要 --repo OWNER/REPO 与 --pr-number N。")
    github = GitHubClient()
    if args.diff_file:
        diff_path = Path(args.diff_file)
        if not diff_path.exists():
            raise GitEngineError(f"Diff 文件不存在：{diff_path}")
        diff_text = diff_path.read_text(encoding="utf-8", errors="replace")
    else:
        repo_obj = github.get_repository(args.repo)
        pr = repo_obj.get_pull(args.pr_number)
        diff_text = github.get_compare_patch(args.repo, pr.base.sha, pr.head.sha)
    if not diff_text.strip():
        print("PR 无代码变更，跳过审查。")
        return 0
    report = AIEngine().review_code(diff_text, repo_context=f"{args.repo} PR #{args.pr_number}")
    print(report)
    result = github.post_or_update_review_comment(
        args.repo, args.pr_number, report + "\n\n" + AI_REVIEW_MARKER
    )
    print(f"✓ 审查报告已发布：{result['url']}")
    return 0


def cmd_check_config(args) -> int:
    """检查配置完整性与 GitHub 连通性。"""
    issues = validate_config(verbose=True)
    if settings_has_token():
        try:
            client = GitHubClient()
            print(f"✓ GitHub 登录成功：{client.authenticate()}（来源：{client.source}）")
        except Exception as exc:  # noqa: BLE001
            print(f"✖ GitHub 连接失败：{exc}")
            issues.append("GitHub 连接失败")
    return 1 if issues else 0


def settings_has_token() -> bool:
    """是否有可用 GitHub 凭证（供 check-config 使用）。"""
    from config import settings

    return bool(settings.github_token)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="GitHub-AI-Studio 无头 CLI（定时任务 / CI 使用）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"GitHub-AI-Studio v{VERSION}")
    parser.add_argument("--daily-push", action="store_true", help="执行每日热榜流水线（无界面）")
    parser.add_argument("--schedule-daily", action="store_true", help="一键配置每日 09:00 定时任务")
    parser.add_argument("--schedule-time", default="09:00", metavar="HH:MM", help="定时任务时间")
    parser.add_argument("--review-pr", action="store_true", help="AI 审查 PR 并回复（供 Actions 使用）")
    parser.add_argument("--repo", metavar="OWNER/REPO", help="仓库全名（配合 --review-pr）")
    parser.add_argument("--pr-number", type=int, help="PR 编号（配合 --review-pr）")
    parser.add_argument("--diff-file", metavar="FILE", help="PR diff 文件（配合 --review-pr）")
    parser.add_argument("--check-config", action="store_true", help="检查配置")
    parser.add_argument("--verbose", action="store_true", help="调试日志")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    setup_logging(verbose=args.verbose)
    try:
        if args.daily_push:
            return cmd_daily_push(args)
        if args.schedule_daily:
            return cmd_schedule_daily(args)
        if args.review_pr:
            return cmd_review_pr(args)
        if args.check_config:
            return cmd_check_config(args)
        parser.print_help()
        return 0
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).exception("CLI 执行失败")
        print(f"✖ {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
