# -*- coding: utf-8 -*-
"""
GitHub-AI-Studio 桌面窗口启动器
================================

把 Streamlit 界面（与之前浏览器版完全相同的渲染效果）嵌入原生桌面窗口：
    - 使用 pywebview（Windows WebView2）创建独立窗口，无地址栏/标签页；
    - 后台线程启动本地 Streamlit 服务，窗口关闭即自动退出；
    - pywebview 不可用时自动回退为 Edge --app 应用窗口模式。

运行：
    python desktop_app.py                # 开发模式（桌面窗口）
    python desktop_app.py --debug        # 调试：用系统浏览器打开
    python desktop_app.py --smoke        # 仅验证服务可启动（CI/自检）

打包：
    python build_exe.py                  # 产出 dist/GitHub-AI-Studio.exe（--windowed）
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

# 打包后 __file__ 指向临时解压目录，日志应写到 EXE 所在目录
if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parent

# 让 PyInstaller 分析到全部项目模块：
# desktop_app 是打包入口，必须直接 import app/config，否则 config/ui/services/core
# 不会被收入 EXE（运行时 Streamlit 脚本会报 ModuleNotFoundError）。
import app  # noqa: F401,E402
import config  # noqa: F401,E402


def _find_free_port() -> int:
    """获取一个空闲本地端口。"""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _acquire_single_instance() -> bool:
    """Windows 命名互斥体：防止多开导致端口/窗口堆叠。

    已有一个实例在运行时返回 False（本次启动直接退出）；
    非 Windows 或无权限时不做限制。
    """
    if os.name != "nt":
        return True
    try:
        import ctypes

        # 使用会话级 Local\ 命名空间：非管理员也能创建，且能阻止本会话重复启动
        handle = ctypes.windll.kernel32.CreateMutexW(
            None, False, "Local\\GitHubAIStudioDesktopApp"
        )
        if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            return False
        # 句柄必须常驻，防止被垃圾回收后互斥体失效
        globals()["_single_instance_mutex"] = handle
        return True
    except Exception:  # noqa: BLE001 —— 互斥失败不阻塞启动
        return True


def _setup_tls_bundle() -> None:
    """确保打包版能找到 CA 证书（certifi 数据随 EXE 解压到 _MEIPASS）。

    PyInstaller 环境下 certifi.where() 指向临时解压目录；显式设置
    SSL_CERT_FILE / REQUESTS_CA_BUNDLE，避免 urllib3 报
    "Could not find a suitable TLS CA certificate bundle"。
    """
    try:
        import certifi

        bundle = certifi.where()
        if Path(bundle).exists():
            os.environ.setdefault("SSL_CERT_FILE", bundle)
            os.environ.setdefault("REQUESTS_CA_BUNDLE", bundle)
    except Exception:  # noqa: BLE001
        pass


def _preload_trending_in_background() -> None:
    """0-Click 后台预加载：静默抓取今日热榜 + AI 分析并写入本地缓存。

    纯后台线程执行，失败只记日志，不阻塞桌面窗口打开；
    UI 打开时直接读 data/trending_cache.json，实现秒开。
    """

    def _work() -> None:
        try:
            from services.trending_service import fetch_and_analyze_only

            result = fetch_and_analyze_only()
            _log(f"后台预加载热榜缓存：{'成功 ' + str(len(result.items)) + ' 条' if result.success else '失败 ' + result.error}")
        except Exception:  # noqa: BLE001
            _log("后台预加载热榜缓存异常（忽略）")

    threading.Thread(target=_work, daemon=True).start()


def _app_path() -> Path:
    """定位 Streamlit 入口 app.py（打包后位于 _MEIPASS 解压目录）。"""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS")) / "app.py"
    return PROJECT_ROOT / "app.py"


def _log(message: str) -> None:
    """写入诊断日志（桌面版无控制台，日志用于排查）。"""
    try:
        log_dir = PROJECT_ROOT / "logs"
        log_dir.mkdir(exist_ok=True)
        with open(log_dir / "desktop.log", "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except OSError:
        pass


def _start_streamlit(port: int) -> threading.Thread:
    """在后台线程中启动本地 Streamlit 服务。

    说明：Streamlit 的 bootstrap 会在非主线程注册 signal 处理器而报错，
    这里按官方嵌入方式屏蔽该注册（服务器本身不受影响）。
    """
    def _run() -> None:
        """在线程中运行 Streamlit，异常写入日志便于排查。"""
        try:
            import traceback

            if getattr(sys, "frozen", False):
                # 打包版无控制台：把 Streamlit 输出重定向到日志文件，便于排错
                log_dir = PROJECT_ROOT / "logs"
                log_dir.mkdir(exist_ok=True)
                stream_log = open(log_dir / "streamlit.log", "a", encoding="utf-8")
                sys.stdout = stream_log
                sys.stderr = stream_log
            import streamlit.web.bootstrap as bootstrap
            import streamlit.web.cli as stcli

            bootstrap._set_up_signal_handler = lambda server: None
            if getattr(sys, "frozen", False):
                os.chdir(str(Path(getattr(sys, "_MEIPASS"))))  # 保证深色主题配置生效
            sys.argv = [
                "streamlit", "run",
                str(_app_path()),
                "--server.headless", "true",
                "--server.address", "127.0.0.1",
                "--server.port", str(port),
                "--server.fileWatcherType", "none",
                "--global.developmentMode", "false",
                "--browser.gatherUsageStats", "false",
            ]
            _log(f"Streamlit 开始运行，入口 {sys.argv[2]}")
            stcli.main()
        except Exception:  # noqa: BLE001
            _log("Streamlit 线程异常：\n" + traceback.format_exc())

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    _log(f"Streamlit 线程已启动（端口 {port}）")
    return thread


def _wait_ready(port: int, timeout: float = 60.0) -> bool:
    """轮询 Streamlit 健康检查接口，直到服务就绪。

    注意：必须绕过代理（ProxyHandler({})）。.env 中的 HTTPS_PROXY 会被
    load_dotenv 写入环境变量，若代理软件未启动，健康检查会全部连接失败。
    """
    import urllib.request

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        try:
            with opener.open(f"http://127.0.0.1:{port}/_stcore/health", timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            time.sleep(0.5)
    _log(f"健康检查超时，最后错误：{last_error}")
    return False


def _open_edge_app(url: str) -> None:
    """回退方案：用 Edge --app 模式打开应用窗口（无浏览器 UI）。"""
    candidates = [
        shutil.which("msedge"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    edge = next((p for p in candidates if p and Path(p).exists()), None)
    if edge:
        subprocess.Popen([edge, f"--app={url}"])
    else:
        webbrowser.open(url)


def main() -> None:
    """启动桌面窗口。"""
    parser = argparse.ArgumentParser(description="GitHub-AI-Studio 桌面窗口")
    parser.add_argument("--port", type=int, default=0, help="Streamlit 端口（默认自动分配）")
    parser.add_argument("--debug", action="store_true", help="用系统浏览器打开（调试模式）")
    parser.add_argument("--smoke", action="store_true", help="仅验证服务可启动后退出")
    args = parser.parse_args()

    if not _acquire_single_instance():
        _log("检测到已有实例在运行，本次启动直接退出")
        return

    port = args.port or _find_free_port()
    _log(f"启动桌面应用，端口 {port}，frozen={getattr(sys, 'frozen', False)}")
    _setup_tls_bundle()
    _start_streamlit(port)
    try:
        if not _wait_ready(port):
            _log("Streamlit 服务启动失败")
            print(f"❌ Streamlit 服务启动失败（端口 {port}）")
            sys.exit(1)
        if args.smoke:
            print(f"SMOKE_OK port={port}")
            return

        # 启动每日自动推送调度器（进程内单例，界面修改时间即时生效）
        try:
            from core.scheduler import DailyPushScheduler

            DailyPushScheduler.ensure_started()
        except Exception:  # noqa: BLE001
            _log("APScheduler 启动失败（忽略）")

        # 0-Click 预加载：UI 秒开，抓取与 AI 分析在后台静默完成
        _preload_trending_in_background()

        url = f"http://127.0.0.1:{port}"
        if args.debug:
            webbrowser.open(url)
            # 调试模式：保持进程存活以维持本地 Streamlit 服务
            try:
                while True:
                    time.sleep(10)
            except KeyboardInterrupt:
                pass
            return

        try:
            import webview  # pywebview

            webview.create_window(
                "GitHub-AI-Studio",
                url,
                width=1280,
                height=820,
                min_size=(960, 620),
                background_color="#0E1117",
            )
            webview.start()  # 阻塞至窗口关闭
        except Exception as exc:  # noqa: BLE001
            print(f"pywebview 不可用（{exc}），回退 Edge 应用窗口模式")
            _open_edge_app(url)
            try:
                while True:
                    time.sleep(10)
            except KeyboardInterrupt:
                pass
    finally:
        _log("桌面应用退出")


if __name__ == "__main__":
    main()
