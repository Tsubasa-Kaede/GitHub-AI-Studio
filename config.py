# -*- coding: utf-8 -*-
"""
GitHub-AI-Studio 统一配置管理
==============================

职责：
    1. 加载 .env（并支持通过 API 写入 .env，供 Streamlit 设置面板使用）；
    2. 优先检测 gh CLI 授权状态，未配置 GITHUB_TOKEN 时自动复用 gh 凭证；
    3. 集中管理 OpenAI / GitHub / Ntfy / 飞书 / Notion 等全部配置；
    4. 提供配置校验与按需获取（缺失时抛出中文 ConfigError）。

该模块不依赖任何 UI / Service / Core 层，属于全局入口。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dotenv import load_dotenv, set_key

# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------
# PyInstaller 打包后 __file__ 指向临时解压目录，配置应定位到 exe 所在目录
if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parent
# 打包后 exe 位于 dist/，若其目录没有 .env，则回退读取项目根目录的 .env
if not (PROJECT_ROOT / ".env").exists():
    parent_env = PROJECT_ROOT.parent / ".env"
    if parent_env.exists():
        PROJECT_ROOT = parent_env.parent
ENV_FILE = PROJECT_ROOT / ".env"
LOG_DIR = PROJECT_ROOT / "logs"

# ---------------------------------------------------------------------------
# .env 自动创建（缺失时不中断程序）
# ---------------------------------------------------------------------------
ENV_TEMPLATE = """# GitHub-AI-Studio 环境变量（自动生成，缺失时创建）
GITHUB_TOKEN=
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
OPENAI_BASE_URL=
USER_INTERESTS=AI Agent, Python, Rust, DevTools
DEFAULT_REPO_VISIBILITY=private
DEFAULT_BRANCH=main
REQUEST_TIMEOUT=30
TRENDING_SINCE=daily
TRENDING_FETCH_LIMIT=25
TRENDING_TOP_N=3
NTFY_SERVER=https://ntfy.sh
NTFY_TOPIC=
NTFY_TOKEN=
NTFY_ARCHIVE_WEBHOOK=
FEISHU_WEBHOOK=
FEISHU_SECRET=
DINGTALK_WEBHOOK=
DINGTALK_SECRET=
WECHAT_WEBHOOK=
EMAIL_SMTP_HOST=
EMAIL_SMTP_PORT=465
EMAIL_USER=
EMAIL_PASSWORD=
EMAIL_TO=
NOTION_TOKEN=
NOTION_DATABASE_ID=
AI_FALLBACK_ENABLED=true
AUTO_PUSH_ENABLED=true
AUTO_PUSH_TIME=08:30
"""


def ensure_env_file() -> Path:
    """若 .env 不存在，则从 .env.example（或内置模板）自动创建。

    只创建、绝不覆盖已有文件；任何 I/O 失败仅静默跳过，不中断程序。
    """
    if ENV_FILE.exists():
        return ENV_FILE
    try:
        template = PROJECT_ROOT / ".env.example"
        content = template.read_text(encoding="utf-8") if template.exists() else ENV_TEMPLATE
        ENV_FILE.write_text(content, encoding="utf-8")
    except OSError:
        pass
    return ENV_FILE


# 加载 .env（不覆盖进程内已存在的环境变量，便于 CI/定时任务注入）
ensure_env_file()
load_dotenv(ENV_FILE, override=False)


class ConfigError(RuntimeError):
    """配置错误：必需凭证缺失或格式非法时抛出。"""


# ---------------------------------------------------------------------------
# 环境变量工具
# ---------------------------------------------------------------------------
def _env(name: str, default: str = "") -> str:
    value = os.getenv(name, default)
    return value.strip() if isinstance(value, str) else default


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"环境变量 {name} 必须是整数，当前值: {raw!r}") from exc


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name).lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"环境变量 {name} 必须是布尔值（true/false），当前值: {raw!r}")


def _parse_interests(raw: str, default: List[str]) -> List[str]:
    """把 'AI Agent, Python、Rust' 解析为标签列表（兼容中英文分隔符）。"""
    if not raw.strip():
        return list(default)
    parts = re.split(r"[,，、;；|]", raw)
    return [p.strip() for p in parts if p.strip()]


# ---------------------------------------------------------------------------
# GitHub 凭证三级自动侦测
# ① .env / 环境变量 GITHUB_TOKEN（由 load_settings 处理）
# ② gh auth token 命令（gh CLI 已登录）
# ③ 解析 ~/.config/gh/hosts.yml（命令不可用时的兜底）
# ---------------------------------------------------------------------------
def _get_gh_token_from_cli() -> Optional[str]:
    """通过 `gh auth token` 命令获取凭证；gh 未安装/未登录返回 None。"""
    if shutil.which("gh") is None:
        return None
    try:
        result = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, timeout=10
        )
        token = result.stdout.strip()
        return token if result.returncode == 0 and token else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _get_gh_token_from_hosts_yml() -> Optional[str]:
    """解析 ~/.config/gh/hosts.yml 中 github.com 段的 oauth_token（轻量正则解析）。"""
    try:
        hosts_path = Path.home() / ".config" / "gh" / "hosts.yml"
    except RuntimeError:
        return None
    if not hosts_path.is_file():
        return None
    try:
        text = hosts_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    # 只取 github.com 主机段，避免误读 enterprise 等其他主机
    section = re.search(r"(?ms)^\s*github\.com\s*:\s*(.*?)(?=^\S|\Z)", text)
    if not section:
        return None
    match = re.search(r"oauth_token\s*:\s*['\"]?([A-Za-z0-9_\-]+)", section.group(1))
    return match.group(1) if match else None


@lru_cache(maxsize=1)
def get_gh_token() -> Optional[str]:
    """按优先级获取 gh CLI 凭证：命令优先，hosts.yml 兜底。"""
    return _get_gh_token_from_cli() or _get_gh_token_from_hosts_yml()


# ---------------------------------------------------------------------------
# 配置对象
# ---------------------------------------------------------------------------
@dataclass
class Settings:
    """全局配置快照。

    注意：采用「就地更新」策略（reload_settings 原地修改字段），
    保证所有已导入本对象的模块无需重启即可感知配置变更。
    """

    github_token: str
    github_token_source: str          # env / gh-cli / none
    github_username: str
    openai_api_key: str
    openai_model: str
    openai_base_url: str
    user_interests: List[str]
    default_repo_visibility: str
    default_branch: str
    request_timeout: int
    trending_since: str
    trending_fetch_limit: int
    trending_top_n: int
    ntfy_server: str
    ntfy_topic: str
    ntfy_token: str
    ntfy_archive_webhook: str
    feishu_webhook: str
    feishu_secret: str
    dingtalk_webhook: str
    dingtalk_secret: str
    wechat_webhook: str
    email_smtp_host: str
    email_smtp_port: int
    email_user: str
    email_password: str
    email_to: str
    notion_token: str
    notion_database_id: str
    ai_fallback_enabled: bool
    auto_push_enabled: bool
    auto_push_time: str


def load_settings() -> Settings:
    """从环境变量构建配置对象（自动融合 gh CLI 凭证）。"""
    visibility = _env("DEFAULT_REPO_VISIBILITY", "private").strip().lower()
    if visibility not in {"public", "private"}:
        raise ConfigError(f"DEFAULT_REPO_VISIBILITY 只能是 public/private，当前值: {visibility!r}")

    since = _env("TRENDING_SINCE", "daily").strip().lower()
    if since not in {"daily", "weekly", "monthly"}:
        raise ConfigError(f"TRENDING_SINCE 只能是 daily/weekly/monthly，当前值: {since!r}")

    # GitHub 凭证三级自动侦测：① .env / 环境变量 → ② gh auth token → ③ hosts.yml
    token = _env("GITHUB_TOKEN")
    source = "env" if token else "none"
    if not token:
        cli_token = _get_gh_token_from_cli()
        if cli_token:
            token, source = cli_token, "gh-cli"
    if not token:
        hosts_token = _get_gh_token_from_hosts_yml()
        if hosts_token:
            token, source = hosts_token, "gh-hosts"

    return Settings(
        github_token=token,
        github_token_source=source,
        github_username=_env("GITHUB_USERNAME"),
        openai_api_key=_env("OPENAI_API_KEY"),
        openai_model=_env("OPENAI_MODEL", "gpt-4o-mini"),
        openai_base_url=_env("OPENAI_BASE_URL"),
        user_interests=_parse_interests(
            _env("USER_INTERESTS"), ["AI Agent", "Python", "DevTools"]
        ),
        default_repo_visibility=visibility,
        default_branch=_env("DEFAULT_BRANCH", "main"),
        request_timeout=_env_int("REQUEST_TIMEOUT", 30),
        trending_since=since,
        trending_fetch_limit=_env_int("TRENDING_FETCH_LIMIT", 25),
        trending_top_n=_env_int("TRENDING_TOP_N", 3),
        ntfy_server=_env("NTFY_SERVER", "https://ntfy.sh"),
        ntfy_topic=_env("NTFY_TOPIC"),
        ntfy_token=_env("NTFY_TOKEN"),
        ntfy_archive_webhook=_env("NTFY_ARCHIVE_WEBHOOK"),
        feishu_webhook=_env("FEISHU_WEBHOOK"),
        feishu_secret=_env("FEISHU_SECRET"),
        dingtalk_webhook=_env("DINGTALK_WEBHOOK"),
        dingtalk_secret=_env("DINGTALK_SECRET"),
        wechat_webhook=_env("WECHAT_WEBHOOK"),
        email_smtp_host=_env("EMAIL_SMTP_HOST"),
        email_smtp_port=_env_int("EMAIL_SMTP_PORT", 465),
        email_user=_env("EMAIL_USER"),
        email_password=_env("EMAIL_PASSWORD"),
        email_to=_env("EMAIL_TO"),
        notion_token=_env("NOTION_TOKEN"),
        notion_database_id=_env("NOTION_DATABASE_ID"),
        ai_fallback_enabled=_env_bool("AI_FALLBACK_ENABLED", True),
        auto_push_enabled=_env_bool("AUTO_PUSH_ENABLED", True),
        auto_push_time=_env("AUTO_PUSH_TIME", "08:30"),
    )


def update_env_file(updates: Dict[str, str]) -> List[str]:
    """写入 / 更新 .env 中的变量（不存在则追加），返回实际变更的键列表。

    供 Streamlit 设置面板与 CLI 使用；写入后同步更新进程内环境变量，
    保证同一次会话内立即生效。
    """
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not ENV_FILE.exists():
        ENV_FILE.write_text("# GitHub-AI-Studio 环境变量\n", encoding="utf-8")
    changed: List[str] = []
    for key, value in updates.items():
        if value is None:
            continue
        old = _env(key)
        set_key(str(ENV_FILE), key, str(value).strip())
        os.environ[key] = str(value).strip()
        if old != str(value).strip():
            changed.append(key)
    if changed:
        reload_settings()
    return changed


def reload_settings() -> Settings:
    """重新从环境变量构建配置，并就地更新全局 settings 对象。"""
    global settings
    new = load_settings()
    for field_name in settings.__dataclass_fields__:
        object.__setattr__(settings, field_name, getattr(new, field_name))
    return settings


def resolve_github_token() -> Tuple[str, str]:
    """返回 (token, source)；未配置任何凭证时抛出 ConfigError。"""
    if settings.github_token:
        return settings.github_token, settings.github_token_source
    raise ConfigError(
        "未配置 GITHUB_TOKEN，且未检测到 gh CLI 登录。"
        "请先在 .env 填写 Token，或执行 gh auth login。"
    )


def require_openai_api_key() -> str:
    """返回 OpenAI Key；缺失时抛出 ConfigError（AI 功能将降级）。"""
    if settings.openai_api_key:
        return settings.openai_api_key
    raise ConfigError("未配置 OPENAI_API_KEY，AI 功能不可用（将自动降级为本地规则）。")


def validate_config(verbose: bool = True) -> List[str]:
    """全量检查配置，返回问题列表（不抛出异常）。"""
    issues: List[str] = []
    if not settings.github_token:
        issues.append("GITHUB_TOKEN 未配置（且 gh CLI 未登录）")
    elif settings.github_token_source == "gh-cli":
        issues.append("GITHUB_TOKEN 未配置，但已自动复用 gh CLI 凭证")
    if not settings.openai_api_key:
        issues.append("OPENAI_API_KEY 未配置（AI 功能将降级为本地规则）")
    if settings.trending_top_n < 1:
        issues.append("TRENDING_TOP_N 必须 >= 1")
    if verbose and issues:
        for issue in issues:
            print(f"[config] ⚠️  {issue}")
    return issues


# 模块级单例
settings: Settings = load_settings()
