# -*- coding: utf-8 -*-
"""
多渠道推送引擎包（core/notifier）
==================================

对外统一导出：
    BaseNotifier / NTFYNotifier / FeishuCardNotifier /
    DingTalkNotifier / WeChatWorkNotifier / EmailNotifier /
    NotifierManager / build_trending_digest

实现位于 core/push_engine.py，本包仅做命名空间兼容：
    from core.notifier import NotifierManager, BaseNotifier
"""

from core.push_engine import (
    BaseNotifier,
    DingTalkNotifier,
    EmailNotifier,
    FeishuCardNotifier,
    NTFYNotifier,
    NotifierManager,
    WeChatWorkNotifier,
    build_trending_digest,
)

__all__ = [
    "BaseNotifier",
    "DingTalkNotifier",
    "EmailNotifier",
    "FeishuCardNotifier",
    "NTFYNotifier",
    "NotifierManager",
    "WeChatWorkNotifier",
    "build_trending_digest",
]
