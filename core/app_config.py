# -*- coding: utf-8 -*-
"""
应用级配置（data/config.json）
==============================

统一保存：
    system.language           界面语言（zh_CN / en_US）
    system.user_tech_stack    个人技术偏好多选标签
    system.auto_push_enabled / auto_push_time   每日推送计划（与 .env 双写）
    channels                  NotifierManager 的多渠道推送配置

所有读写均为原子写（临时文件 + replace），失败只记日志不中断。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config import PROJECT_ROOT, settings
from core.i18n import normalize_lang

logger = logging.getLogger(__name__)

STATE_FILE: Path = PROJECT_ROOT / "data" / "config.json"
LEGACY_CHANNEL_FILE: Path = PROJECT_ROOT / "data" / "notifiers.json"

DEFAULT_TECH_STACK: List[str] = [
    "LLM / Agent",
    "RAG / 知识库",
    "Python",
    "ComfyUI / AIGC",
    "Rust / Go",
    "前端 / Web3",
    "计算机视觉 (CV)",
    "数据工程",
    "嵌入式 / IoT",
]


def _default_state() -> dict:
    """默认状态（优先从 .env 读取推送计划）。"""
    return {
        "system": {
            "language": "zh_CN",
            "user_tech_stack": list(DEFAULT_TECH_STACK[:3]),
            "auto_push_enabled": bool(settings.auto_push_enabled),
            "auto_push_time": settings.auto_push_time or "08:30",
        },
        "channels": {},
    }


def _read_raw() -> dict:
    """读取 config.json；文件缺失/损坏返回默认状态。"""
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("读取 data/config.json 失败：%s", exc)
    return _default_state()


def _write_raw(state: dict) -> bool:
    """原子写入 config.json。"""
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(STATE_FILE)
        return True
    except OSError as exc:
        logger.warning("写入 data/config.json 失败：%s", exc)
        return False


# ---------------------------------------------------------------------------
# system 段
# ---------------------------------------------------------------------------
def get_language() -> str:
    return normalize_lang(_read_raw().get("system", {}).get("language", "zh_CN"))


def set_language(lang: str) -> bool:
    state = _read_raw()
    state.setdefault("system", {})["language"] = normalize_lang(lang)
    return _write_raw(state)


def get_tech_stack() -> List[str]:
    raw = _read_raw().get("system", {}).get("user_tech_stack")
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    return list(settings.user_interests) or list(DEFAULT_TECH_STACK[:3])


def set_tech_stack(tags: List[str]) -> bool:
    state = _read_raw()
    state.setdefault("system", {})["user_tech_stack"] = [t.strip() for t in tags if t.strip()]
    return _write_raw(state)


def get_push_plan() -> Tuple[bool, str]:
    system = _read_raw().get("system", {})
    return bool(system.get("auto_push_enabled", settings.auto_push_enabled)), (
        system.get("auto_push_time") or settings.auto_push_time or "08:30"
    )


def set_push_plan(enabled: bool, time_str: str) -> bool:
    state = _read_raw()
    state.setdefault("system", {}).update({
        "auto_push_enabled": bool(enabled),
        "auto_push_time": time_str,
    })
    return _write_raw(state)


# ---------------------------------------------------------------------------
# channels 段（NotifierManager 使用；兼容旧 data/notifiers.json）
# ---------------------------------------------------------------------------
def get_channels() -> dict:
    state = _read_raw()
    channels = state.get("channels")
    if isinstance(channels, dict) and channels:
        return channels
    # 迁移旧文件
    if LEGACY_CHANNEL_FILE.exists():
        try:
            legacy = json.loads(LEGACY_CHANNEL_FILE.read_text(encoding="utf-8"))
            if isinstance(legacy, dict):
                return legacy
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("读取旧 notifiers.json 失败：%s", exc)
    return {}


def set_channels(channels: dict) -> bool:
    state = _read_raw()
    state["channels"] = channels
    return _write_raw(state)
