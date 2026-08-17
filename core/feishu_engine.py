# -*- coding: utf-8 -*-
"""
飞书自定义机器人推送引擎
========================

通过飞书自定义机器人 Webhook 发送交互式卡片（msg_type: "interactive"）：
    - 蓝色 Header + 「🚀 GitHub 今日热榜 & AI 技能风向标」标题；
    - 顶栏渲染 AI 提取的【今日技能雷达】；
    - 逐条渲染项目名（带 GitHub 链接）、Star 数、语言标签、AI 核心学习点；
    - 可选 secret 签名校验（HMAC-SHA256）。

安全约定：所有 requests 请求统一 timeout=(3.0, 5.0)，异常全部捕获并返回
(False, "错误说明")，绝不抛出异常导致 Streamlit 崩溃。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
from typing import List, Optional, Sequence, Tuple

import requests

from config import settings
from models import TrendingRepo

logger = logging.getLogger(__name__)


class FeishuEngineError(RuntimeError):
    """飞书推送错误（保留兼容；实际方法均返回元组而非抛出）。"""


class FeishuEngine:
    """飞书自定义机器人推送器（交互式卡片）。"""

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        secret: Optional[str] = None,
        timeout: Optional[Tuple[float, float]] = None,
    ):
        self.webhook_url = webhook_url or settings.feishu_webhook
        self.secret = secret if secret is not None else settings.feishu_secret
        # 连接 3s / 读取 5s，避免 UI 长时间阻塞
        self.timeout = timeout if timeout is not None else (3.0, 5.0)

    @property
    def configured(self) -> bool:
        """是否已配置 Webhook URL（secret 可选）。"""
        return bool(self.webhook_url and self.webhook_url.startswith("https://"))

    # ------------------------------------------------------------------
    def _sign(self, timestamp: str) -> Optional[str]:
        """飞书机器人签名：HMAC-SHA256(timestamp + '\\n' + secret) 的 Base64。"""
        if not self.secret:
            return None
        try:
            string_to_sign = f"{timestamp}\n{self.secret}"
            hmac_code = hmac.new(
                string_to_sign.encode("utf-8"), digestmod=hashlib.sha256
            ).digest()
            return base64.b64encode(hmac_code).decode("utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.warning("飞书签名失败：%s", exc)
            return None

    def _post(self, payload: dict) -> Tuple[bool, str]:
        """发送请求；任何异常都转为 (False, 错误说明)，绝不抛出。"""
        if not self.configured:
            return (False, "未配置 FEISHU_WEBHOOK_URL（需 https 地址），请在「⚙️ 设置」中填写。")
        try:
            resp = requests.post(
                self.webhook_url,
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code", 0) != 0:
                return (False, f"飞书返回错误：{data.get('msg') or data.get('code')}")
            return (True, "推送成功")
        except requests.Timeout as exc:
            return (False, f"飞书请求超时（连接 3s / 读取 5s）：{exc}")
        except requests.RequestException as exc:
            return (False, f"飞书请求失败：{exc}")
        except ValueError as exc:
            return (False, f"飞书返回内容无法解析：{exc}")
        except Exception as exc:  # noqa: BLE001 —— 兜底，保证 UI 不崩
            return (False, f"飞书推送异常：{exc}")

    # ------------------------------------------------------------------
    def send_card(self, card: dict) -> Tuple[bool, str]:
        """发送任意交互式卡片（payload 为 msg_type: interactive 结构）。"""
        payload = {"msg_type": "interactive", "card": card}
        if self.secret:
            timestamp = str(int(time.time()))
            sign = self._sign(timestamp)
            if sign:
                payload["timestamp"] = timestamp
                payload["sign"] = sign
        return self._post(payload)

    # ------------------------------------------------------------------
    def send_trending_digest(
        self, repos: Sequence[TrendingRepo], skills_radar: Optional[Sequence[str]] = None
    ) -> Tuple[bool, str]:
        """发送「今日热榜 & AI 技能风向标」交互式卡片。"""
        repos = list(repos)
        if not repos:
            return (False, "没有热榜数据，无法构造飞书卡片。")

        radar = [str(t) for t in (skills_radar or []) if str(t).strip()]
        elements: List[dict] = [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**📡 今日技能雷达**：{'  '.join(radar) or '（AI 未生成，待刷新）'}",
                },
            },
            {"tag": "hr"},
        ]
        for i, repo in enumerate(repos, start=1):
            learning = repo.learning_points or repo.zh_summary or repo.description or "（暂无学习点）"
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**{i}. [{repo.name}]({repo.url})**\n"
                        f"⭐ {repo.stars_total:,} Stars · 🏷️ {repo.language or '多语言'}\n"
                        f"🎯 学习点：{learning[:120]}"
                    ),
                },
            })
            elements.append({"tag": "hr"})

        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "blue",
                "title": {
                    "tag": "plain_text",
                    "content": "🚀 GitHub 今日热榜 & AI 技能风向标",
                },
            },
            "elements": elements,
        }
        return self.send_card(card)

    # ------------------------------------------------------------------
    def test(self) -> dict:
        """连通性测试：发送一张最小测试卡片，返回 {"ok", "message", "elapsed_ms"}。"""
        start = time.perf_counter()
        ok, message = self.send_card({
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "blue",
                "title": {"tag": "plain_text", "content": "GitHub-AI-Studio 连接测试"},
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": "✅ 飞书机器人配置正确，推送链路已打通。"}}
            ],
        })
        return {
            "ok": ok,
            "message": message if not ok else "测试卡片已发送",
            "elapsed_ms": int((time.perf_counter() - start) * 1000),
        }

    # ------------------------------------------------------------------
    @staticmethod
    def _fmt_stars(num: int) -> str:
        """56.2k 形式格式化 Star 数。"""
        num = num or 0
        if num >= 1_000_000:
            return f"{num / 1_000_000:.1f}M"
        if num >= 1_000:
            return f"{num / 1_000:.1f}k"
        return str(num)
