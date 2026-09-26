# 更新日志（Changelog）

本项目的所有重要变更记录于此。格式参考 Keep a Changelog，版本遵循语义化版本。

## [1.0.0] - 2026-09-13

首个公开版本。

### 新增

- 独立桌面控制台：PyWebView 内嵌 Streamlit，7 大功能 Tab，深色终端风主题
- 一键托管：本地目录 → AI 多语言 README（zh-CN/en/ja）→ 建仓 → Commit & Push
- AI 智能 Commit：密钥扫描 + OSV 依赖漏洞扫描 + Conventional Commits 生成
- 中文热榜：AI 评分/标签/防直译翻译、深度研读、技能雷达与 30s 简报、
  Master-Detail 看板（存入待学 / 移回新榜 / Notion 归档）
- 自动发版：Git 历史 → AI CHANGELOG 分类 → GitHub Release 发布
- Star 语义搜索：自然语言检索已 Star 仓库
- 工作日报：今日/本周提交 → 结构化 Markdown 日报
- 多渠道推送：Ntfy / 飞书 / 钉钉 / 企业微信 / 邮件；Notion 归档
- 系统托盘常驻 + 每日定时推送（APScheduler，多进程防重）
- 无头 CLI：每日推送、定时任务配置、PR AI 审查、配置检查
- 多模型支持：COMMIT_MODEL / TRENDING_MODEL 场景覆盖 +
  OPENAI_FALLBACK_MODEL 降级链（限流/超时自动切换）
- 分发：Inno Setup 安装包（快捷方式 + 卸载器）与便携版单文件 EXE
- CI：GitHub Actions，Ubuntu/Windows × Python 3.12/3.13 矩阵（ruff + 43 测试）

### 修复

- 一键托管 AI 降级路径的 NameError（AIEngineError 未导入）
- 自动发版页对 widget 已占用 session key 赋值导致的 StreamlitAPIException
- 混合版本标签（v1.0 / 1.2）排序 TypeError
- Master-Detail 重构时丢失的「移回新榜」入口
- 热榜 Star 数 m 后缀解析为 0
- 每日推送多进程重复触发（当日标记防重）
- 非法 .env 配置项在导入期崩溃（回退默认值并汇报）
- AIEngine 多线程懒加载 OpenAI 客户端的竞态
- 文本截断句中断裂（硬切补省略号）
