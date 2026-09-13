# -*- coding: utf-8 -*-
"""
GitHub-AI-Studio 系统托盘常驻服务
==================================

功能：
    1. pystray 系统托盘图标（右下角常驻）；
    2. 「🔥 立刻抓取并推送」——后台线程执行热榜流水线（AI 评分翻译 → Ntfy 手机推送
       → Notion 归档），完成后 plyer 桌面 Toast 弹窗；
    3. 「🖥️ 打开控制台」——拉起 `desktop_app.py`（PyWebView 桌面控制台）；
    4. 「❌ 退出后台服务」——停止每日调度并退出托盘；
    5. APScheduler 每日自动执行全自动热榜推送（时间可在控制台界面修改）。

运行：
    python tray.py            # 开发调试
    pythonw tray.py           # Windows 静默运行（推荐）
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

# 保证以任意工作目录启动时都能找到项目模块
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pystray  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from config import settings  # noqa: E402
from services.trending_service import run_daily_trending_pipeline  # noqa: E402

logger = logging.getLogger(__name__)

ACTION_FETCH = "立刻抓取并推送"
ACTION_OPEN = "打开控制台"
ACTION_EXIT = "退出后台服务"

# ---------------------------------------------------------------------------
# 图标（Pillow 程序化绘制）
# ---------------------------------------------------------------------------
def _build_icon() -> Image.Image:
    """绘制 128x128 托盘图标：深色圆角底 + 紫色星形。"""
    img = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([6, 6, 122, 122], radius=30,
                           fill=(22, 26, 38, 255), outline=(124, 92, 255, 255), width=5)
    draw.polygon(
        [(64, 16), (72, 46), (104, 54), (72, 62), (64, 96), (56, 62), (24, 54), (56, 46)],
        fill=(124, 92, 255, 255),
    )
    draw.ellipse([54, 42, 74, 62], fill=(240, 242, 245, 255))
    return img


# ---------------------------------------------------------------------------
# 桌面通知（plyer）
# ---------------------------------------------------------------------------
def notify(title: str, message: str) -> None:
    """系统 Toast 弹窗；失败仅记日志，不中断托盘。"""
    try:
        from plyer import notification

        notification.notify(title=title, message=message, app_name="GitHub-AI-Studio", timeout=10)
    except Exception as exc:  # noqa: BLE001
        logger.warning("桌面通知失败：%s", exc)


# ---------------------------------------------------------------------------
# 热榜任务
# ---------------------------------------------------------------------------
def run_trending_job() -> None:
    """后台线程执行热榜流水线 → Ntfy 推送 → plyer Toast。"""

    def _work() -> None:
        logger.info("开始执行热榜流水线（托盘触发）...")
        try:
            result = run_daily_trending_pipeline()
            if result.success:
                lines = [f"{r.name}（{r.stars_total:,}⭐）" for r in result.items]
                sent = result.pushed_channels.get("sent", 0) if result.pushed_channels else 0
                notify(
                    "GitHub 热榜已推送",
                    "\n".join(lines[:3]) + f"\nNtfy 推送 {sent}/{len(result.items)} 条",
                )
                logger.info("热榜完成：%d 条，推送 %s，Notion %s",
                            len(result.items), result.pushed_channels, result.notion_page_url)
            else:
                notify("热榜推送失败", result.error)
        except Exception as exc:  # noqa: BLE001
            logger.exception("热榜任务异常")
            notify("热榜任务异常", str(exc))

    threading.Thread(target=_work, daemon=True).start()


# ---------------------------------------------------------------------------
# 唤起桌面控制台（独立窗口）
# ---------------------------------------------------------------------------
def open_console() -> None:
    """打开独立桌面控制台窗口（优先打包好的 EXE，其次 pythonw 运行 desktop_app.py）。"""

    def _work() -> None:
        target = str(PROJECT_ROOT / "desktop_app.py")
        exe = PROJECT_ROOT / "dist" / "GitHub-AI-Studio.exe"
        try:
            if os.name == "nt":
                if exe.exists():
                    subprocess.Popen([str(exe)], cwd=str(PROJECT_ROOT))
                else:
                    pythonw = Path(sys.executable).with_name("pythonw.exe")
                    subprocess.Popen([str(pythonw), target], cwd=str(PROJECT_ROOT))
            elif sys.platform == "darwin":
                # macOS：通过 Terminal.app 打开新窗口
                if exe.exists():
                    command = f'cd "{PROJECT_ROOT}" && "{exe}"'
                else:
                    command = f'cd "{PROJECT_ROOT}" && python3 desktop_app.py'
                subprocess.Popen([
                    "osascript", "-e", f'tell app "Terminal" to do script "{command}"'
                ])
            else:
                # Linux：优先 x-terminal-emulator
                term = os.environ.get("TERMINAL", "x-terminal-emulator")
                cmd = [str(exe)] if exe.exists() else [sys.executable, target]
                subprocess.Popen([term, "-e", *cmd], cwd=str(PROJECT_ROOT))
            logger.info("已打开桌面控制台")
        except OSError as exc:
            logger.error("唤起桌面控制台失败：%s", exc)
            notify("控制台启动失败", str(exc))

    threading.Thread(target=_work, daemon=True).start()


# ---------------------------------------------------------------------------
# 托盘菜单回调
# ---------------------------------------------------------------------------
def _on_fetch(icon, item) -> None:
    run_trending_job()


def _on_open(icon, item) -> None:
    open_console()


def _on_exit(icon, item) -> None:
    logger.info("收到退出指令，正在清理...")
    try:
        from core.scheduler import DailyPushScheduler

        DailyPushScheduler.shutdown()
    except Exception:  # noqa: BLE001
        pass
    icon.stop()


# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="GitHub-AI-Studio 系统托盘服务")
    parser.add_argument("--time", default=None, help="每日自动推送时间（HH:MM，默认读取 AUTO_PUSH_TIME）")
    args = parser.parse_args()

    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(log_dir / "tray.log", encoding="utf-8")],
    )

    # 启动 APScheduler 每日定时任务（时间与开关可在控制台界面实时修改）
    from core.scheduler import DailyPushScheduler

    DailyPushScheduler.ensure_started()
    if args.time:
        ok, message = DailyPushScheduler.update_schedule(settings.auto_push_enabled, args.time)
        logger.info("%s（%s）", message, args.time if ok else "忽略参数")

    menu = pystray.Menu(
        pystray.MenuItem(ACTION_FETCH, _on_fetch),
        pystray.MenuItem(ACTION_OPEN, _on_open),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(ACTION_EXIT, _on_exit),
    )
    icon = pystray.Icon("GitHub-AI-Studio", _build_icon(), "GitHub-AI-Studio 后台服务", menu)
    logger.info("托盘服务已启动：每日自动推送 %s", settings.auto_push_time)
    icon.run()
    logger.info("托盘服务已退出。")


if __name__ == "__main__":
    main()
