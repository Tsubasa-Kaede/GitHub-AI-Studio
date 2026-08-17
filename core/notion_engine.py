# -*- coding: utf-8 -*-
"""
Notion 归档引擎
================

通过 Notion REST API 将热榜项目写入指定数据库页面。
数据库需预先建好，并包含属性：
    项目名称(title) / 中文定位(rich_text) / Star数(number) /
    AI摘要(rich_text) / GitHub链接(url) / 日期(date)
"""

from __future__ import annotations

from datetime import date
import logging
from typing import Dict, Optional

import requests

from config import settings
from models import TrendingRepo

NOTION_API = "https://api.notion.com/v1"
logger = logging.getLogger(__name__)


class NotionEngineError(RuntimeError):
    """Notion API 操作失败。"""


class NotionArchiver:
    """Notion 数据库写入器。"""

    def __init__(self, token: Optional[str] = None, database_id: Optional[str] = None, timeout: Optional[int] = None):
        self.token = token or settings.notion_token
        self.database_id = database_id or settings.notion_database_id
        self.timeout = timeout or settings.request_timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
            "User-Agent": "GitHub-AI-Studio/1.0",
        })

    @property
    def configured(self) -> bool:
        """是否已配置 Token 与数据库 ID。"""
        return bool(self.token and self.database_id)

    def validate(self) -> bool:
        """校验数据库可访问（GET /databases/{id}）。"""
        if not self.configured:
            raise NotionEngineError("未配置 NOTION_TOKEN / NOTION_DATABASE_ID。")
        try:
            resp = self.session.get(
                f"{NOTION_API}/databases/{self.database_id}", timeout=self.timeout
            )
            resp.raise_for_status()
            return True
        except requests.RequestException as exc:
            raise NotionEngineError(f"Notion 数据库校验失败：{exc}") from exc

    def test(self) -> dict:
        """连通性测试：读取数据库 Schema 验证权限，返回 {"ok", "message", "elapsed_ms"}。"""
        import time

        if not self.configured:
            return {
                "ok": False,
                "message": "未配置 NOTION_TOKEN / NOTION_DATABASE_ID",
                "elapsed_ms": 0,
            }
        start = time.perf_counter()
        try:
            self.validate()
            return {
                "ok": True,
                "message": "数据库可访问，权限正常",
                "elapsed_ms": int((time.perf_counter() - start) * 1000),
            }
        except NotionEngineError as exc:
            return {
                "ok": False,
                "message": str(exc),
                "elapsed_ms": int((time.perf_counter() - start) * 1000),
            }

    def archive_trending(self, repo: TrendingRepo) -> Optional[str]:
        """把单个热榜项目写入数据库，返回页面 URL。"""
        if not self.configured:
            raise NotionEngineError("未配置 NOTION_TOKEN / NOTION_DATABASE_ID，跳过归档。")
        payload = {"parent": {"database_id": self.database_id}, "properties": self._build_properties(repo)}
        try:
            resp = self.session.post(f"{NOTION_API}/pages", json=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            return data.get("url")
        except requests.RequestException as exc:
            detail = ""
            try:
                detail = resp.json().get("message", "")
            except Exception:  # noqa: BLE001
                pass
            raise NotionEngineError(f"Notion 归档失败：{exc} {detail}".strip()) from exc

    def archive_many(self, repos) -> Dict[str, str]:
        """批量归档，返回 {repo_name: page_url}；单个失败不阻断其余。"""
        results: Dict[str, str] = {}
        for repo in repos:
            try:
                url = self.archive_trending(repo)
                if url:
                    results[repo.name] = url
            except NotionEngineError as exc:
                logger.warning("归档 %s 失败：%s", repo.name, exc)
                continue
        return results

    # ------------------------------------------------------------------
    def _build_properties(self, repo: TrendingRepo) -> dict:
        """把 TrendingRepo 映射为 Notion 数据库属性。"""
        return {
            "项目名称": {"title": [{"text": {"content": repo.name}}]},
            "中文定位": {"rich_text": [{"text": {"content": repo.zh_position or "开源项目"}}]},
            "Star数": {"number": repo.stars_total or repo.stars_today},
            "AI摘要": {"rich_text": [{"text": {"content": (repo.zh_summary or repo.description or "")[:1900]}}]},
            "GitHub链接": {"url": repo.url},
            "日期": {"date": {"start": date.today().isoformat()}},
        }
