# -*- coding: utf-8 -*-
"""
每日自动推送调度器（APScheduler）
=================================

职责：
    1. 使用 BackgroundScheduler + CronTrigger(hour, minute) 每天定时执行
       「抓取热榜 → 组装 AI 趋势日报 → 多渠道推送 → Notion 归档」；
    2. 提供 update_schedule(enabled, time_str)：Streamlit 界面修改时间/开关时
       实时 reschedule 任务，无需重启程序；
    3. 进程内单例（ensure_started 幂等），桌面壳 / 托盘 / Streamlit 共用。

配置项（.env）：
    AUTO_PUSH_ENABLED=true|false（默认 true）
    AUTO_PUSH_TIME=HH:MM（默认 08:30）
"""

from __future__ import annotations

import logging
import re
import threading
from datetime import date
from pathlib import Path
from typing import Optional, Tuple

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from config import PROJECT_ROOT, settings

logger = logging.getLogger(__name__)

# 每日推送防重标记：托盘/桌面壳/任务计划程序是多个独立进程，
# 各自都可能有调度器在跑，用「当日已推送」标记避免同一台机器重复推送。
PUSH_MARKER_FILE: Path = PROJECT_ROOT / "data" / ".last_daily_push"


def already_pushed_today(marker_file: Optional[Path] = None) -> bool:
    """今天是否已经成功执行过每日推送。"""
    path = marker_file or PUSH_MARKER_FILE
    try:
        return path.read_text(encoding="utf-8").strip() == date.today().isoformat()
    except OSError:
        return False


def _mark_pushed_today(marker_file: Optional[Path] = None) -> None:
    """写入当日推送标记（失败只记日志，不阻断流程）。"""
    path = marker_file or PUSH_MARKER_FILE
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(date.today().isoformat(), encoding="utf-8")
    except OSError as exc:
        logger.warning("写入每日推送标记失败：%s", exc)


def _run_daily_push_job() -> None:
    """定时任务体：按技术偏好抓取热榜 → 双语 AI 日报 → 多通道推送 → Notion 归档。"""
    if already_pushed_today():
        logger.info("今日推送已完成（其他进程已执行），跳过本次重复触发。")
        return
    logger.info("⏰ 触发每日自动推送任务...")
    try:
        from core import app_config
        from core.i18n import translate
        from core.notion_engine import NotionArchiver
        from core.push_engine import NotifierManager, build_trending_digest
        from services.trending_service import fetch_and_analyze_only

        lang = app_config.get_language()
        interests = app_config.get_tech_stack() or list(settings.user_interests)
        result = fetch_and_analyze_only(interests=interests)
        if not result.success:
            logger.error("每日推送：抓取/翻译失败：%s", result.error)
            return

        digest = build_trending_digest(result.items)
        results = NotifierManager().dispatch_all(
            translate("push.digest_title", lang), digest
        )
        logger.info(
            "每日推送：按偏好 %s 筛选 %d 条，渠道结果：%s",
            interests, len(result.items), results,
        )

        archiver = NotionArchiver()
        if archiver.configured:
            urls = archiver.archive_many(result.items)
            logger.info("每日推送：Notion 归档 %d 条", len(urls))

        # 抓取与推送流程走完才打标记；抓取失败当天由其他进程/下次触发兜底
        _mark_pushed_today()
    except Exception as exc:  # noqa: BLE001 —— 任务异常只记日志，不影响调度器
        logger.exception("每日推送任务异常：%s", exc)


class DailyPushScheduler:
    """进程内单例调度器。"""

    JOB_ID = "daily_trending_push"
    _scheduler: Optional[BackgroundScheduler] = None
    _lock = threading.Lock()

    # ------------------------------------------------------------------
    @classmethod
    def _get_scheduler(cls) -> BackgroundScheduler:
        """幂等启动调度器（仅启动，不应用计划）。"""
        with cls._lock:
            if cls._scheduler is None or not cls._scheduler.running:
                scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
                scheduler.start()
                cls._scheduler = scheduler
                logger.info("APScheduler 已启动")
            return cls._scheduler

    @classmethod
    def _apply_schedule(cls, enabled: bool, time_str: str) -> Tuple[bool, str]:
        """把计划应用到已启动的调度器（不启动、不再递归）。"""
        if not re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", time_str):
            return (False, f"时间格式不合法：{time_str!r}（应为 HH:MM）")

        scheduler = cls._scheduler
        if scheduler is None or not scheduler.running:
            return (False, "调度器未启动")
        job = scheduler.get_job(cls.JOB_ID)
        if not enabled:
            if job is not None:
                job.remove()
                logger.info("已关闭每日自动推送")
            return (True, "已关闭每日自动推送")

        hour, minute = (int(x) for x in time_str.split(":"))
        trigger = CronTrigger(hour=hour, minute=minute)
        if job is not None:
            job.reschedule(trigger=trigger)
            logger.info("每日自动推送已改为 %s", time_str)
        else:
            scheduler.add_job(
                _run_daily_push_job,
                trigger,
                id=cls.JOB_ID,
                replace_existing=True,
                max_instances=1,
                misfire_grace_time=3600,
            )
            logger.info("每日自动推送已注册：%s", time_str)
        return (True, f"✅ 推送时间已更新为 {time_str}")

    @classmethod
    def ensure_started(cls) -> BackgroundScheduler:
        """幂等启动调度器，并按当前 .env 配置注册每日任务。"""
        scheduler = cls._get_scheduler()
        cls._apply_schedule(settings.auto_push_enabled, settings.auto_push_time)
        return scheduler

    @classmethod
    def update_schedule(
        cls, enabled: Optional[bool] = None, time_str: Optional[str] = None
    ) -> Tuple[bool, str]:
        """实时更新每日推送计划；返回 (成功, 说明)。"""
        enabled = settings.auto_push_enabled if enabled is None else bool(enabled)
        time_str = settings.auto_push_time if not time_str else str(time_str).strip()
        cls._get_scheduler()  # 未启动时先启动
        return cls._apply_schedule(enabled, time_str)

    @classmethod
    def next_run(cls) -> Optional[str]:
        """下次触发时间（未启用返回 None）。"""
        scheduler = cls._scheduler
        if scheduler is None or not scheduler.running:
            return None
        job = scheduler.get_job(cls.JOB_ID)
        if job is None:
            return None
        return job.next_run_time.isoformat() if job.next_run_time else None

    @classmethod
    def shutdown(cls) -> None:
        """停止调度器（托盘退出时调用）。"""
        with cls._lock:
            if cls._scheduler is not None and cls._scheduler.running:
                cls._scheduler.shutdown(wait=False)
                logger.info("APScheduler 已停止")
