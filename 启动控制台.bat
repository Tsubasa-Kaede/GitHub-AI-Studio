@echo off
chcp 65001 >nul
rem ============================================================
rem GitHub-AI-Studio 独立界面控制台启动器
rem 双击本文件即打开桌面窗口应用
rem ============================================================
cd /d "%~dp0"

if exist "dist\GitHub-AI-Studio.exe" (
    start "" "dist\GitHub-AI-Studio.exe"
) else (
    start "" pythonw desktop_app.py
)
exit /b
