# GitHub-AI-Studio 架构设计说明

## 一、两个候选方案的对比结论

### 方案 A（扁平结构）

**优点**：文件少、上手快、`core/` 直接放 `trending_notifier` / `release_generator`，简单直接。

**问题**：
- `trending_notifier` 同时负责“抓取 + 筛选 + 通知”，职责混杂，难以单独测试与替换；
- 缺少 DTO 层，数据以裸 dict 传递，字段名靠约定；
- UI 与 CLI 职责边界未定义（规格中只有 `app.py` 与 `--daily-push`，没有独立 CLI 层）；
- `release_generator` 与 `notion_archiver` 是典型业务流水线，放在 core 层违背“原子引擎”定位。

### 方案 B（Clean Architecture）

**优点**：严格分层（UI → Services → Core → Models），依赖方向清晰：
- `models.py` 用 Dataclass 规范数据形状；
- `services/` 编排原子能力，UI 与 CLI 可复用同一流水线；
- `core/` 只保留无业务语义的原子引擎（git / github / ai / push / notion）；
- 可测试性、可扩展性明显优于方案 A。

**不足**：文件较多，初次理解成本略高——但以“长期维护”为目标，这是值得的。

### 最终设计

**以方案 B 为骨架**，吸收方案 A 的实用点：

| 来源 | 吸收内容 |
| --- | --- |
| 方案 B | 分层结构、models.py、services 流水线、CLI 独立入口 |
| 方案 A | 热榜双端能力（手机 + Notion）、Release 生成器（并入 release_service）、.env 写回 |
| 旧项目经验 | 敏感信息拦截、gh CLI 凭证复用、--schedule-daily 定时配置、PR 审查 CLI 模式 |

## 二、旧项目（GitHub-AI-Manager）审查与改进对照

| 旧项目问题 | 新项目改进 |
| --- | --- |
| 无 UI，功能全在 CLI 菜单 | Streamlit 控制台 + 7 Tab，深色主题 |
| 逻辑散落在 `cli.py` 与 `core/`，无流水线层 | `services/` 三个流水线，UI/CLI 共用 |
| 数据用裸 dict 传递 | `models.py` Dataclass（TrendingRepo / ReleaseInfo） |
| 不识别 `gh auth login` 凭证 | config 优先检测 gh CLI，其次 .env Token |
| .env 只能读不能写 | `update_env_file()` 支持 UI 保存写回 |
| 热榜模块同时负责抓取/筛选/桌面通知 | `trending_service` 编排，core 只留原子能力 |
| Release 生成逻辑内嵌在 cli.py | `release_service`（Extract → Format → Publish） |
| 无 Notion 归档 | `notion_engine` + 双端归档按钮 |
| 手机推送渠道过多（4 个） | 收敛为 Ntfy + 飞书，另支持钉钉 / 企微 / 邮件，保留扩展点 |
| 部分 AI 调用靠文本解析 | 全部结构化输出（response_format=json_object） |
| 错误类型命名不统一 | 各引擎统一 `*Error`，UI 用 `st.error`，CLI 用日志 |
| 敏感扫描缺 Fine-grained Token | 已补 `github_pat_` 模式并沿用 |

## 三、数据流示例（每日热榜）

```text
Trending 页面/搜索 API
        │ fetch_github_trending()
        ▼
List[TrendingRepo]（原始英文）
        │ AIEngine.select_and_translate_trending()   ← JSON 结构化
        ▼
List[TrendingRepo]（中文定位 + 摘要）
        │ PushEngine.send_trending()  ──► Ntfy / 飞书
        │ NotionArchiver.archive_many() ──► Notion 数据库
        ▼
PipelineResult（UI / CLI 统一消费）
```
