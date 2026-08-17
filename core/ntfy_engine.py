# -*- coding: utf-8 -*-
"""
Ntfy.sh 手机推送引擎
====================

Ntfy 是开源的 Push 服务：手机安装 Ntfy App 订阅 Topic 后即可收到锁屏通知。
本引擎支持「通知栏 Actions 按钮」：
    - view 动作：点击直接调起浏览器打开 GitHub 仓库；
    - http 动作：点击自动 POST 归档 Webhook（配合服务端完成 Notion 归档）。

请求方式：JSON Body（原生 UTF-8，中文标题/内容不会触发 latin-1 编码错误）。
    - URL 固定为 Ntfy 根服务地址（如 https://ntfy.sh），不拼接 /topic；
    - topic 放入 JSON Body 的 "topic" 字段；
    - 序列化使用 json.dumps(payload, ensure_ascii=False).encode('utf-8')，
      中文与 Emoji 以原文传输，不会变成 \\uXXXX 转义形式。
Actions 内部仍以 CSV 字符串传递，发送前解析为 JSON 对象：
    view, 打开 GitHub, <URL>; http, 归档 Notion, <WEBHOOK>, method=POST
"""

from __future__ import annotations

import json
import logging
from typing import Dict, List, Optional

import requests

from config import settings
from models import TrendingRepo

logger = logging.getLogger(__name__)


class NtfyEngineError(RuntimeError):
    """Ntfy 推送失败。"""


class NtfyEngine:
    """Ntfy.sh 推送器（带通知栏交互按钮）。"""

    def __init__(
        self,
        server: Optional[str] = None,
        topic: Optional[str] = None,
        token: Optional[str] = None,
        archive_webhook: Optional[str] = None,
        timeout: Optional[tuple] = None,
    ):
        self.server = (server or settings.ntfy_server or "https://ntfy.sh").rstrip("/")
        # 提取根服务地址：防止配置了带路径的 URL（如 https://ntfy.sh/xxx）
        if self.server.count("/") > 2 and not self.server.startswith("http://localhost"):
            self.server = "/".join(self.server.split("/")[:3])
        self.topic = topic or settings.ntfy_topic
        self.token = token if token is not None else settings.ntfy_token
        self.archive_webhook = archive_webhook if archive_webhook is not None else settings.ntfy_archive_webhook
        # 网络请求统一使用短超时：连接 3s / 读取 5s，避免 UI 长时间卡死
        self.timeout = timeout if timeout is not None else (3.0, 5.0)

    @property
    def configured(self) -> bool:
        """是否已配置 Topic（server 有默认值，Topic 是必需项）。"""
        return bool(self.topic)

    # ------------------------------------------------------------------
    def send(
        self,
        title: str,
        message: str,
        url: str = "",
        tags: Optional[List[str]] = None,
        priority: int = 3,
        actions: Optional[List[str]] = None,
    ) -> tuple:
        """发送一条 Ntfy 通知，返回 (成功, 说明)；任何异常都不抛出。"""
        if not self.configured:
            return (False, "未配置 NTFY_TOPIC，请在 .env 或「⚙️ 设置」中填写。")
        # JSON Body 传参：topic/title/message/tags/click/actions 全部走 UTF-8，
        # 不再放进 HTTP Header（Header 仅保留 ASCII 的 Authorization）。
        payload = {
            "topic": self.topic,
            "title": title,
            "message": message,
            "priority": priority,
            "tags": tags or [],
        }
        if url:
            payload["click"] = url  # 点击通知正文直接打开链接
        if actions:
            payload["actions"] = self._parse_actions(actions)
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            # ensure_ascii=False：中文与 Emoji 以原文 UTF-8 传输，不转义为 \\uXXXX
            data_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            resp = requests.post(
                self.server,
                data=data_bytes,
                headers=headers,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return (True, "推送成功")
        except requests.Timeout as exc:
            return (False, f"Ntfy 推送超时（连接 3s / 读取 5s）：{exc}")
        except requests.RequestException as exc:
            return (False, f"Ntfy 推送失败：{exc}")
        except Exception as exc:  # noqa: BLE001 —— 兜底，绝不让异常冒泡到 UI
            return (False, f"Ntfy 推送异常：{exc}")

    @staticmethod
    def _parse_actions(actions: List[str]) -> List[dict]:
        """把 CSV 动作字符串解析为 Ntfy JSON Actions 对象数组。

        示例：
            "view, 打开 GitHub, https://github.com/x" →
                {"action": "view", "label": "打开 GitHub", "url": "https://github.com/x"}
            "http, 归档 Notion, https://webhook, method=POST" →
                {"action": "http", "label": "归档 Notion", "url": "https://webhook", "method": "POST"}
        """
        parsed: List[dict] = []
        for raw in actions or []:
            parts = [part.strip() for part in raw.split(",")]
            if not parts or not parts[0]:
                continue
            action = parts[0].lower()
            if action == "view" and len(parts) >= 3:
                parsed.append({
                    "action": "view",
                    "label": ", ".join(parts[1:-1]),
                    "url": parts[-1],
                })
            elif action == "http" and len(parts) >= 3:
                if len(parts) == 3:
                    label, url, extras = ", ".join(parts[1:-1]), parts[-1], []
                else:
                    label, url, extras = ", ".join(parts[1:-2]), parts[-2], parts[-1:]
                item = {"action": "http", "label": label, "url": url}
                for extra in extras:
                    if "=" in extra:
                        key, value = extra.split("=", 1)
                        item[key.strip()] = value.strip()
                parsed.append(item)
        return parsed

    def test(self) -> dict:
        """连通性测试：发送一条测试通知，返回 {"ok", "message", "elapsed_ms"}。"""
        import time

        if not self.configured:
            return {"ok": False, "message": "未配置 NTFY_TOPIC", "elapsed_ms": 0}
        start = time.perf_counter()
        ok, message = self.send(
            title="GitHub-AI-Studio 连接测试",
            message="✅ 配置正确，通知链路已打通。",
            tags=["tada"],
            priority=4,
        )
        return {
            "ok": ok,
            "message": message if not ok else "测试通知已发送",
            "elapsed_ms": int((time.perf_counter() - start) * 1000),
        }

    # ------------------------------------------------------------------
    def send_trending(self, items: List[TrendingRepo]) -> Dict[str, bool]:
        """逐条推送热榜 Top N，每条通知带「打开 GitHub / 归档 Notion」动作按钮。

        返回 {"ntfy": 是否全部成功, "sent": 成功条数}。
        """
        if not items:
            return {}
        ok_count = 0
        errors: List[str] = []
        for repo in items:
            ok, message = self.send(
                title=f"🔥 {repo.name}（{self._fmt_stars(repo.stars_total)}）",
                message=(
                    f"🎯 {repo.zh_position or '开源项目'}\n"
                    f"💡 {repo.zh_summary or repo.description}\n"
                    f"⭐ {repo.stars_total:,} Stars · {repo.language or '多语言'}"
                ),
                url=repo.url,
                tags=["github", repo.language or "code"],
                actions=self._build_actions(repo),
            )
            if ok:
                ok_count += 1
            else:
                logger.warning("推送 %s 失败：%s", repo.name, message)
                errors.append(f"{repo.name}: {message}")
        return {"ntfy": ok_count == len(items), "sent": ok_count, "errors": errors}

    # ------------------------------------------------------------------
    def _build_actions(self, repo: TrendingRepo) -> List[str]:
        """构建通知栏动作：view 打开 GitHub + http 触发 Notion 归档。"""
        actions = [f"view, 打开 GitHub, {repo.url}"]
        if self.archive_webhook:
            actions.append(f"http, 归档 Notion, {self.archive_webhook}, method=POST")
        return actions

    @staticmethod
    def _fmt_stars(num: int) -> str:
        """56.2k 形式格式化 Star 数。"""
        num = num or 0
        if num >= 1_000_000:
            return f"{num / 1_000_000:.1f}M"
        if num >= 1_000:
            return f"{num / 1_000:.1f}k"
        return str(num)
