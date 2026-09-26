# HelloGitHub 投稿草稿

> 提交入口：https://hellogithub.com/create（登录后「提交项目」，选择合适分类：Python / 桌面）
> 以下内容按表单字段组织，直接复制粘贴。

## 项目名称

GitHub-AI-Studio

## 项目地址

https://github.com/Tsubasa-Kaede/GitHub-AI-Studio

## 项目简介（HelloGitHub 有字数限制，约 100 字内）

本地 GitHub 智能化管理控制台：AI 每天筛选并翻译 GitHub 热榜，生成中文研读看板，可推送到手机锁屏并归档 Notion；同时提供 AI Commit、自动发版、Star 语义搜索等功能。Windows 免安装 EXE，双击即用。

## 一句话推荐语（如果有该字段）

每天 30 秒，AI 帮你读完 GitHub 热榜。

## 详细介绍（如需长文）

「看 GitHub Trending」是每天最费时的动作之一：英文描述、看不出和自己的技术栈有什么关系、看完记不住。这个项目把这件事压缩到 30 秒：

- 后台自动抓取热榜，AI 按你的技术偏好筛选 Top N，生成中文定位、亮点摘要和深度研读（概述 / 痛点 / 核心功能 / 适用场景 / 技术亮点），专有名词保留英文原文
- 打开桌面窗口秒读缓存，不打断手头工作；卡片可「存入待学」形成个人学习看板
- 一键推送到手机锁屏（Ntfy），通勤路上看完今日趋势
- 附带 AI 智能 Commit（密钥扫描 + 依赖漏洞扫描）、AI 生成 CHANGELOG 并发 Release、Star 仓库语义搜索、工作日报

技术上：Python + Streamlit + PyWebView 的本地桌面应用，Clean Architecture 分层，AI 全部走 OpenAI 兼容接口的结构化输出（JSON mode），无 Key 时自动降级为本地规则，流水线不中断。支持按场景覆盖模型和备用模型降级链。

Windows 10/11 提供安装版和便携版 EXE，下载即用，无需 Python 环境。

## 投稿检查清单（对照 writing-guidelines 自查）

- 无 easy/simple/just 类模糊词，具体（"30 秒" "Top N" "双击即用"）
- 主动语态、短句，每句只讲一个意思
- 标题/开头面向用户问题（费时、看不懂、记不住），不是功能罗列
- 列表项非完整句，无句号
- 锚文本说明目的地
