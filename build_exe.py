# -*- coding: utf-8 -*-
"""
PyInstaller 单文件打包脚本
==========================

把 desktop_app.py 打包为免安装的单文件桌面应用（pywebview 内嵌 Streamlit 界面）：
    Windows: dist/GitHub-AI-Studio.exe（--windowed，双击即开独立窗口，无控制台）

使用：
    pip install pyinstaller
    python build_exe.py

说明：config.py 已做 frozen 适配，打包后 .env 会从 exe 所在目录读取。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> None:
    """执行 PyInstaller 打包命令。"""
    # Windows 控制台默认 GBK 编码无法输出 emoji，统一改为 UTF-8
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    project_root = Path(__file__).resolve().parent
    # Windows 使用分号分隔 add-data，Linux/macOS 使用冒号
    sep = ";" if sys.platform == "win32" else ":"
    name, mode, entry = "GitHub-AI-Studio", "--windowed", "desktop_app.py"
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        mode,
        "--name", name,
    ]
    # 桌面版：收集 Streamlit 静态资源与 pywebview 运行时
    cmd += ["--collect-all", "streamlit", "--collect-all", "pywebview", "--collect-all", "certifi"]
    # pywebview 在 Windows 可能依赖 pythonnet / webview2，存在则一并收集
    import importlib.util

    for optional in ("pythonnet", "webview2", "bottle", "proxy_tools"):
        if importlib.util.find_spec(optional) is not None:
            cmd += ["--collect-all", optional]
    cmd += [
        "--add-data", f"requirements.txt{sep}.",
        "--add-data", f"app.py{sep}.",
        "--add-data", f"ui{sep}ui",
        "--add-data", f".streamlit{sep}.streamlit",
        str(project_root / entry),
    ]
    print("执行打包命令：", " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(project_root))
    print("✅ 打包完成：", project_root / "dist" / f"{name}.exe")


if __name__ == "__main__":
    main()
