# -*- coding: utf-8 -*-
"""
多渠道统一推送引擎（Multi-Channel Push Engine）
================================================

架构：
    BaseNotifier（抽象基类）
      ├─ NTFYNotifier         → Ntfy.sh（JSON Body，UTF-8 中文）
      ├─ FeishuCardNotifier   → 飞书交互式卡片
      ├─ DingTalkNotifier     → 钉钉 Markdown（支持加签 HMAC-SHA256）
      ├─ WeChatWorkNotifier   → 企业微信机器人 Markdown
      └─ EmailNotifier        → smtplib HTML 邮件
    NotifierManager           → JSON 配置加载/保存 + 多通道并发发送

安全约定：所有网络请求统一 timeout=(3.0, 5.0)，异常全部捕获并返回 False，
任何渠道失败都不影响其他渠道，也不向 UI 抛出异常。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import logging
import re
import smtplib
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage
from pathlib import Path
from typing import Dict, List, Optional, Sequence
from urllib.parse import quote_plus

import requests

from config import PROJECT_ROOT, settings
from models import TrendingRepo

logger = logging.getLogger(__name__)

TIMEOUT = (3.0, 5.0)  # 连接 3s / 读取 5s


# ---------------------------------------------------------------------------
# 抽象基类
# ---------------------------------------------------------------------------
class BaseNotifier(ABC):
    """统一推送接口：所有渠道驱动必须实现 send()。"""

    name = "base"

    def __init__(self, config: Optional[dict] = None):
        self.config = dict(config or {})
        self.last_error = ""

    @property
    @abstractmethod
    def configured(self) -> bool:
        """渠道是否已配置（未配置时 send 返回 False，不发起请求）。"""

    @abstractmethod
    def send(self, title: str, content_markdown: str, action_url: str = "") -> tuple:
        """发送一条消息，返回 (成功, 说明)；任何异常都吞掉不抛出。"""

    def _fail(self, message: str) -> tuple:
        self.last_error = message
        logger.warning("[%s] %s", self.name, message)
        return (False, message)


# ---------------------------------------------------------------------------
# NTFY
# ---------------------------------------------------------------------------
def _split_ntfy_url(url: str) -> tuple:
    """把 https://ntfy.sh/my_topic 拆为 (server, topic)。"""
    url = (url or "").strip().rstrip("/")
    if not url:
        return "", ""
    # 兼容 server 单独配置：没有路径时 topic 为空
    idx = url.rfind("/")
    if idx <= len("https://"):
        return url, ""
    return url[:idx], url[idx + 1:]


class NTFYNotifier(BaseNotifier):
    """Ntfy.sh：JSON Body 传参，原生 UTF-8，带查看详情 Action。"""

    name = "ntfy"

    @property
    def configured(self) -> bool:
        server, topic = _split_ntfy_url(self.config.get("url", ""))
        return bool(server and topic)

    def send(self, title: str, content_markdown: str, action_url: str = "") -> tuple:
        if not self.configured:
            return self._fail("未配置 NTFY URL（https://ntfy.sh/topic）")
        try:
            from core.ntfy_engine import NtfyEngine

            server, topic = _split_ntfy_url(self.config.get("url", ""))
            engine = NtfyEngine(
                server=server or None,
                topic=topic or None,
                token=self.config.get("token") or None,
                timeout=TIMEOUT,
            )
            ok, message = engine.send(
                title=title,
                message=content_markdown,
                url=action_url or "",
                priority=int(self.config.get("priority", 3) or 3),
                tags=["github"],
                actions=[f"view, 查看详情, {action_url}"] if action_url else None,
            )
            if not ok:
                return self._fail(message)
            return (True, "推送成功")
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"NTFY 异常：{exc}")


# ---------------------------------------------------------------------------
# 飞书
# ---------------------------------------------------------------------------
class FeishuCardNotifier(BaseNotifier):
    """飞书交互式卡片（msg_type: interactive，蓝色 Header）。"""

    name = "feishu"

    @property
    def configured(self) -> bool:
        url = (self.config.get("webhook") or "").strip()
        return bool(url and url.startswith("https://"))

    def send(self, title: str, content_markdown: str, action_url: str = "") -> tuple:
        if not self.configured:
            return self._fail("未配置飞书 Webhook URL")
        try:
            from core.feishu_engine import FeishuEngine

            body = content_markdown
            if action_url:
                body += f"\n\n[🔗 查看详情]({action_url})"
            card = {
                "config": {"wide_screen_mode": True},
                "header": {
                    "template": "blue",
                    "title": {"tag": "plain_text", "content": title[:50]},
                },
                "elements": [
                    {"tag": "div", "text": {"tag": "lark_md", "content": body[:4000]}}
                ],
            }
            ok, message = FeishuEngine(
                webhook_url=self.config.get("webhook") or None,
                secret=self.config.get("secret") or None,
            ).send_card(card)
            if not ok:
                return self._fail(message)
            return (True, "推送成功")
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"飞书异常：{exc}")


# ---------------------------------------------------------------------------
# 钉钉
# ---------------------------------------------------------------------------
class DingTalkNotifier(BaseNotifier):
    """钉钉自定义机器人 Markdown（可选加签 HMAC-SHA256）。"""

    name = "dingtalk"

    @property
    def configured(self) -> bool:
        return bool((self.config.get("webhook") or "").strip())

    @staticmethod
    def _sign(timestamp: str, secret: str) -> str:
        """钉钉加签：HMAC-SHA256(key=secret, msg=timestamp\\nsecret) 的 Base64。"""
        string_to_sign = f"{timestamp}\n{secret}"
        hmac_code = hmac.new(
            secret.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha256
        ).digest()
        return base64.b64encode(hmac_code).decode("utf-8")

    def send(self, title: str, content_markdown: str, action_url: str = "") -> tuple:
        webhook = (self.config.get("webhook") or "").strip()
        if not webhook:
            return self._fail("未配置钉钉 Webhook")
        secret = (self.config.get("secret") or "").strip()
        text = content_markdown
        if action_url:
            text += f"\n\n[🔗 查看详情]({action_url})"
        payload = {"msgtype": "markdown", "markdown": {"title": title[:64], "text": text[:8000]}}
        url = webhook
        if secret:
            timestamp = str(int(time.time() * 1000))
            url += f"&timestamp={timestamp}&sign={quote_plus(self._sign(timestamp, secret))}"
        try:
            resp = requests.post(url, json=payload, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if data.get("errcode", 0) != 0:
                return self._fail(f"钉钉返回错误：{data.get('errmsg')}")
            return (True, "推送成功")
        except requests.Timeout as exc:
            return self._fail(f"钉钉请求超时：{exc}")
        except requests.RequestException as exc:
            return self._fail(f"钉钉请求失败：{exc}")
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"钉钉异常：{exc}")


# ---------------------------------------------------------------------------
# 企业微信
# ---------------------------------------------------------------------------
class WeChatWorkNotifier(BaseNotifier):
    """企业微信机器人 Markdown 消息。"""

    name = "wechat"

    @property
    def configured(self) -> bool:
        return bool((self.config.get("webhook") or "").strip())

    def send(self, title: str, content_markdown: str, action_url: str = "") -> tuple:
        webhook = (self.config.get("webhook") or "").strip()
        if not webhook:
            return self._fail("未配置企业微信 Webhook")
        text = f"## {title}\n{content_markdown}"
        if action_url:
            text += f"\n<a href='{action_url}'>🔗 查看详情</a>"
        payload = {"msgtype": "markdown", "markdown": {"content": text[:4000]}}
        try:
            resp = requests.post(webhook, json=payload, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if data.get("errcode", 0) != 0:
                return self._fail(f"企业微信返回错误：{data.get('errmsg')}")
            return (True, "推送成功")
        except requests.Timeout as exc:
            return self._fail(f"企业微信请求超时：{exc}")
        except requests.RequestException as exc:
            return self._fail(f"企业微信请求失败：{exc}")
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"企业微信异常：{exc}")


# ---------------------------------------------------------------------------
# 邮件
# ---------------------------------------------------------------------------
def _markdown_to_html(text: str) -> str:
    """极简 Markdown → HTML（转义 + 加粗 + 链接 + 换行），足够邮件阅读。"""
    lines = []
    for line in (text or "").splitlines():
        escaped = html.escape(line)
        escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
        escaped = re.sub(r"\[(.+?)\]\((https?://[^\s)]+)\)", r'<a href="\2">\1</a>', escaped)
        lines.append(escaped)
    return "<br>".join(lines)


class EmailNotifier(BaseNotifier):
    """smtplib HTML 邮件（端口 465 走 SSL，否则 STARTTLS）。"""

    name = "email"

    @property
    def configured(self) -> bool:
        cfg = self.config
        return bool(cfg.get("smtp_host") and cfg.get("user") and cfg.get("password") and cfg.get("to"))

    def send(self, title: str, content_markdown: str, action_url: str = "") -> tuple:
        cfg = self.config
        if not self.configured:
            return self._fail("邮件配置不完整（smtp_host/user/password/to 均需填写）")
        body = content_markdown
        if action_url:
            body += f"\n\n[🔗 查看详情]({action_url})"
        message = EmailMessage()
        message["Subject"] = title
        message["From"] = cfg["user"]
        message["To"] = cfg["to"]
        message.set_content(body)
        message.add_alternative(
            f"<html><body style='font-family:sans-serif;line-height:1.6;'>{_markdown_to_html(body)}</body></html>",
            subtype="html",
        )
        try:
            port = int(cfg.get("smtp_port", 465) or 465)
            host = cfg["smtp_host"]
            if port == 465:
                with smtplib.SMTP_SSL(host, port, timeout=5.0) as server:
                    server.login(cfg["user"], cfg["password"])
                    server.send_message(message)
            else:
                with smtplib.SMTP(host, port, timeout=5.0) as server:
                    server.starttls()
                    server.login(cfg["user"], cfg["password"])
                    server.send_message(message)
            return (True, "推送成功")
        except Exception as exc:  # noqa: BLE001
            return self._fail(f"邮件发送失败：{exc}")


# ---------------------------------------------------------------------------
# 配置与管理
# ---------------------------------------------------------------------------
DEFAULT_NOTIFIER_CONFIG = {
    "ntfy": {"enabled": False, "url": "", "priority": 3, "token": ""},
    "feishu": {"enabled": False, "webhook": "", "secret": ""},
    "dingtalk": {"enabled": False, "webhook": "", "secret": ""},
    "wechat": {"enabled": False, "webhook": ""},
    "email": {
        "enabled": False, "smtp_host": "", "smtp_port": 465,
        "user": "", "password": "", "to": "",
    },
}


class NotifierManager:
    """多通道配置管理 + 并发发送。配置存于 data/config.json 的 channels 段。"""

    CONFIG_FILE: Path = PROJECT_ROOT / "data" / "config.json"
    _drivers: Dict[str, type] = {
        "ntfy": NTFYNotifier,
        "feishu": FeishuCardNotifier,
        "dingtalk": DingTalkNotifier,
        "wechat": WeChatWorkNotifier,
        "email": EmailNotifier,
    }

    def __init__(self, config: Optional[dict] = None):
        self.config = config if config is not None else self.load_config()

    # ------------------------------------------------------------------
    @classmethod
    def load_config(cls) -> dict:
        """读取 channels 配置（含旧 notifiers.json 迁移）；缺失时用 .env 种子值。"""
        from core import app_config

        channels = app_config.get_channels()
        if channels:
            return cls._normalize(channels)
        default = cls._default_config()
        app_config.set_channels(default)
        return default

    @classmethod
    def _default_config(cls) -> dict:
        """用 .env 现有配置作为种子。"""
        cfg = json.loads(json.dumps(DEFAULT_NOTIFIER_CONFIG))
        if settings.ntfy_server and settings.ntfy_topic:
            cfg["ntfy"]["url"] = f"{settings.ntfy_server.rstrip('/')}/{settings.ntfy_topic}"
            cfg["ntfy"]["enabled"] = True
        if settings.feishu_webhook:
            cfg["feishu"]["webhook"] = settings.feishu_webhook
            cfg["feishu"]["secret"] = settings.feishu_secret
            cfg["feishu"]["enabled"] = True
        if settings.dingtalk_webhook:
            cfg["dingtalk"]["webhook"] = settings.dingtalk_webhook
            cfg["dingtalk"]["secret"] = settings.dingtalk_secret
            cfg["dingtalk"]["enabled"] = True
        if settings.wechat_webhook:
            cfg["wechat"]["webhook"] = settings.wechat_webhook
            cfg["wechat"]["enabled"] = True
        if settings.email_smtp_host and settings.email_user and settings.email_password and settings.email_to:
            cfg["email"]["smtp_host"] = settings.email_smtp_host
            cfg["email"]["smtp_port"] = settings.email_smtp_port
            cfg["email"]["user"] = settings.email_user
            cfg["email"]["password"] = settings.email_password
            cfg["email"]["to"] = settings.email_to
            cfg["email"]["enabled"] = True
        return cls._normalize(cfg)

    @staticmethod
    def _normalize(data: dict) -> dict:
        cfg = json.loads(json.dumps(DEFAULT_NOTIFIER_CONFIG))
        for name, defaults in DEFAULT_NOTIFIER_CONFIG.items():
            item = data.get(name)
            if isinstance(item, dict):
                cfg[name].update({k: v for k, v in item.items() if k in defaults})
        return cfg

    def save_config(self) -> None:
        """原子写入 config.json 的 channels 段（保留 system 段）。"""
        from core import app_config

        app_config.set_channels(self.config)

    # ------------------------------------------------------------------
    def get_driver(self, name: str) -> Optional[BaseNotifier]:
        item = self.config.get(name)
        driver_cls = self._drivers.get(name)
        if not item or not driver_cls:
            return None
        return driver_cls(item)

    def available_channels(self) -> List[str]:
        """返回已启用且配置完整的渠道名。"""
        channels = []
        for name in self._drivers:
            driver = self.get_driver(name)
            item = self.config.get(name, {})
            if item.get("enabled") and driver and driver.configured:
                channels.append(name)
        return channels

    def send_all(self, title: str, content_markdown: str, action_url: str = "") -> Dict[str, bool]:
        """并发发送到全部已启用渠道；单渠道失败不影响其他渠道。"""
        self.last_errors: Dict[str, str] = {}
        channels = self.available_channels()
        if not channels:
            logger.warning("没有已启用的推送渠道（data/config.json 的 channels 段）")
            return {}
        results: Dict[str, bool] = {}

        def _send(name: str) -> tuple:
            driver = self.get_driver(name)
            if driver is None:
                return name, False, "驱动不存在"
            ok, message = driver.send(title, content_markdown, action_url)
            return name, ok, message

        with ThreadPoolExecutor(max_workers=min(len(channels), 5)) as pool:
            futures = [pool.submit(_send, name) for name in channels]
            for future in futures:
                name, ok, message = future.result()
                results[name] = ok
                if not ok:
                    self.last_errors[name] = message
        return results

    def dispatch_all(self, title: str, content_markdown: str, action_url: str = "") -> Dict[str, bool]:
        """dispatch_all 是 send_all 的别名（多渠道并发分发）。"""
        return self.send_all(title, content_markdown, action_url)

    def test_channel(self, name: str) -> dict:
        """向指定渠道发送测试消息，返回 {"ok", "message", "elapsed_ms"}。"""
        driver = self.get_driver(name)
        if driver is None:
            return {"ok": False, "message": f"未知渠道：{name}", "elapsed_ms": 0}
        if not self.config.get(name, {}).get("enabled"):
            return {"ok": False, "message": f"{name} 渠道未启用", "elapsed_ms": 0}
        if not driver.configured:
            return {"ok": False, "message": f"{name} 渠道配置不完整", "elapsed_ms": 0}
        from core.app_config import get_language
        from core.i18n import translate

        lang = get_language()
        start = time.perf_counter()
        ok, message = driver.send(
            translate("push.test_title", lang), translate("push.test_message", lang)
        )
        return {
            "ok": ok,
            "message": "测试消息已发送" if ok else (message or driver.last_error or "发送失败"),
            "elapsed_ms": int((time.perf_counter() - start) * 1000),
        }


# ---------------------------------------------------------------------------
# 每日趋势日报构造
# ---------------------------------------------------------------------------
def build_trending_digest(
    repos: Sequence[TrendingRepo], skills_radar: Optional[Sequence[str]] = None
) -> str:
    """把热榜项目组为多通道通用的标准化日报（项目名原样保留，防过度翻译）。"""
    from core.llm_summary import build_trending_digest as _llm_digest

    return _llm_digest(repos, skills_radar)
