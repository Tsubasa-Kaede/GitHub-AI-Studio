# 已归档的备用 UI（2026-08-09）

当前主入口已统一为：

- `desktop_app.py`（PyWebView 桌面窗口壳）
- `app.py` + `ui/`（Streamlit 控制台界面）

以下文件因功能重复/不再维护而被移出主代码树，**仅归档保留**，不再打包、不再被导入：

| 文件 | 说明 |
| --- | --- |
| `gui_app.py` | 旧版 Tkinter 桌面界面（已被 PyWebView + Streamlit 替代） |
| `main_tui.py` | Textual 终端 TUI 入口（已被桌面窗口替代） |
| `tui/` | Textual 终端视图层（随 TUI 一并归档） |
| `GitHub-AI-Console.spec` | 旧 TUI 版 PyInstaller 配置（可随时删除） |

如确认不再需要，可安全删除整个 `archive/` 目录。
